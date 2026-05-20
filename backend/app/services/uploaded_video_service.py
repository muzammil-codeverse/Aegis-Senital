from __future__ import annotations

import hashlib
import json
import mimetypes
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from app.core.capabilities.defaults import register_default_capabilities
from app.core.capabilities.models import CapabilityState
from app.core.capabilities.registry import get_capability_registry
from app.models.case_models import CaseCreateRequest, CaseEvidenceCreateRequest
from app.models.incident_models import IncidentEventRecord
from app.models.security_models import AuditAction
from app.models.security_models import UserAccount
from app.models.uploaded_video_models import (
    UploadedVideoCaseCreationRequest,
    UploadedVideoEvent,
    UploadedVideoProcessingOptions,
    UploadedVideoProcessingStatus,
    UploadedVideoProgress,
    UploadedVideoReplayClipMetadata,
    UploadedVideoReport,
    UploadedVideoSession,
    UploadedVideoTimelineItem,
    UploadedVideoUploadResponse,
)
from app.repositories.incident_repository import get_incident_repository
from app.security.config import PROJECT_ROOT
from app.security.upload_policy import get_upload_security_policy
from app.services.case_service import get_case_service
from app.services.command_center_intelligence_service import CommandCenterIntelligenceService
from app.services.audit_log_service import get_audit_log_service
from app.services.uploaded_video_progress_service import get_uploaded_video_progress_service
from inference.config_runtime import load_runtime_config
from inference.metrics import metrics
from inference.model_pool import ModelPool
from inference.monitoring.metrics import get_metrics
from inference.stream.stream_processor import StreamProcessor
from ml.runtime import ModelRouter
from app.services.replay_clip_service import (
    UploadedVideoReplayClipError,
    _safe_uploaded_video_event_filename,
    generate_uploaded_video_event_clip_ffmpeg,
    is_ffmpeg_available,
)
from app.services.rtsp_ingest_service import DecodedFramePacket


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user_id(user: UserAccount | str | None) -> str:
    if isinstance(user, UserAccount):
        return str(user.user_id or user.username)
    return str(user or "system")


def _new_session_id() -> str:
    return f"uvs_{uuid.uuid4().hex[:16]}"


def _coerce_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def _metric_increment(name: str, count: int = 1) -> None:
    try:
        get_metrics().increment(name, count)
    except Exception:
        pass
    try:
        metrics.increment(name, count)
    except Exception:
        pass


def _metric_set(name: str, value: int | float) -> None:
    try:
        get_metrics().record_segmentation_value(name, value)
    except Exception:
        pass
    try:
        metrics.set_value(name, value)
    except Exception:
        pass


@dataclass(slots=True)
class _ActiveUploadJob:
    thread: threading.Thread
    cancel_event: threading.Event
    started_at: str
    last_error: str | None = None


class UploadedVideoService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_runtime_config("uploaded_video")
        self._config = dict(self._raw_config.get("uploaded_video") or {})
        self._upload_policy = get_upload_security_policy()
        self._incident_repository = get_incident_repository()
        self._case_service = get_case_service()
        self._progress_service = get_uploaded_video_progress_service()
        self._storage_cfg = dict(self._config.get("storage") or {})
        self._upload_cfg = dict(self._config.get("upload") or {})
        self._processing_cfg = dict(self._config.get("processing") or {})
        self._case_cfg = dict(self._config.get("case_integration") or {})
        self._report_cfg = dict(self._config.get("reporting") or {})
        self._replay_cfg = dict(self._config.get("replay") or {})
        self._root_dir = self._resolve_dir(str(self._storage_cfg.get("root_dir") or "storage/uploaded_videos"))
        self._processed_dir = self._resolve_dir(str(self._storage_cfg.get("processed_dir") or "storage/uploaded_video_results"))
        self._evidence_dir = self._resolve_dir(str(self._storage_cfg.get("evidence_dir") or "storage/evidence"))
        self._command_center_dir = self._resolve_dir(str(self._storage_cfg.get("command_center_dir") or "storage/command_center_intelligence"))
        self._command_center_service = CommandCenterIntelligenceService(
            storage_dir=self._command_center_dir,
            incident_repository=self._incident_repository,
            case_service=self._case_service,
        )
        self._lock = threading.RLock()
        self._jobs: dict[str, _ActiveUploadJob] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", True))

    def _mark_capability(
        self,
        capability_id: str,
        state: CapabilityState | str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        *,
        health_score: float | None = None,
    ) -> None:
        try:
            registry = register_default_capabilities(get_capability_registry())
            registry.update_status(
                capability_id,
                state,
                reason,
                metadata={"uploaded_video": metadata or {}},
                health_score=health_score,
            )
        except Exception:
            pass

    def _mark_capability_faulted(self, capability_id: str, error: Exception | str, metadata: dict[str, Any] | None = None) -> None:
        try:
            registry = register_default_capabilities(get_capability_registry())
            registry.mark_faulted(capability_id, error, {"uploaded_video": metadata or {}})
        except Exception:
            pass

    def _write_processing_status(
        self,
        session: UploadedVideoSession,
        status_value: str,
        *,
        started_at: str | None = None,
        active: bool,
        report_ready: bool = False,
        event_count: int = 0,
        last_error: str | None = None,
    ) -> UploadedVideoProcessingStatus:
        session.status = status_value
        if last_error:
            session.metadata = {
                **(session.metadata or {}),
                "last_error": last_error,
                "last_error_at": _now_iso(),
            }
        self._write_session(session)
        status = UploadedVideoProcessingStatus(
            session_id=session.session_id,
            status=status_value,
            progress=session.progress,
            started_at=started_at,
            completed_at=session.completed_at,
            active=active,
            report_ready=report_ready,
            event_count=event_count,
            last_error=last_error,
        )
        self._write_status(session.session_id, status)
        return status

    def upload_video(
        self,
        file: Any,
        options: UploadedVideoProcessingOptions | dict[str, Any] | None,
        user: UserAccount | str,
    ) -> UploadedVideoUploadResponse:
        if not self.enabled:
            raise RuntimeError("Uploaded-video analysis is disabled")
        upload_options = (
            options
            if isinstance(options, UploadedVideoProcessingOptions)
            else UploadedVideoProcessingOptions.model_validate(options or {})
        )
        filename = getattr(file, "filename", None) or "upload.mp4"
        content_type = getattr(file, "content_type", None)
        content = file.file.read() if hasattr(file, "file") else bytes(file)
        validation = self._upload_policy.validate(
            filename=filename,
            content=content,
            content_type=content_type,
            allowed_classes={"video"},
        )
        session_id = _new_session_id()
        safe_filename = validation.build_storage_name("uploaded_video", session_id)
        storage_path = self._upload_policy.resolve_storage_path(str(self._root_dir.relative_to(PROJECT_ROOT)), safe_filename)
        storage_path.write_bytes(content)
        video_meta = self._video_metadata(storage_path)
        session = UploadedVideoSession(
            session_id=session_id,
            original_filename=validation.normalized_filename,
            safe_filename=safe_filename,
            storage_uri=self._storage_uri(storage_path),
            hash_sha256=validation.sha256 if bool(self._upload_cfg.get("compute_sha256", True)) else hashlib.sha256(content).hexdigest(),
            duration_seconds=float(video_meta.get("duration_seconds") or 0.0),
            frame_count=int(video_meta.get("frame_count") or 0),
            fps=float(video_meta.get("fps") or 0.0),
            status="uploaded",
            progress=UploadedVideoProgress(
                frames_processed=0,
                total_frames=int(video_meta.get("frame_count") or 0),
                percent=0.0,
            ),
            created_by=_safe_user_id(user),
            metadata={
                "content_type": validation.content_type,
                "size_bytes": validation.size_bytes,
                "malware_scan": validation.malware_scan,
                "options": upload_options.model_dump(mode="json"),
            },
        )
        self._write_session(session)
        self._write_json(self._events_path(session.session_id), [])
        self._write_json(self._timeline_path(session.session_id), [])
        status = UploadedVideoProcessingStatus(
            session_id=session.session_id,
            status="uploaded",
            progress=session.progress,
            active=False,
            report_ready=False,
            event_count=0,
        )
        self._write_status(session.session_id, status)
        _metric_increment("uploaded_video_uploads_total")
        return UploadedVideoUploadResponse(session=session, detail="Video uploaded successfully")

    def start_processing(self, session_id: str, user: UserAccount | str) -> UploadedVideoProcessingStatus:
        session = self._require_session(session_id)
        if session.status == "completed":
            return self.get_status(session_id, user)
        with self._lock:
            existing = self._jobs.get(session_id)
            if existing and existing.thread.is_alive():
                return self.get_status(session_id, user)
            cancel_event = threading.Event()
            started_at = _now_iso()
            thread = threading.Thread(
                target=self._process_session_job,
                args=(session_id, cancel_event),
                name=f"uploaded-video-{session_id}",
                daemon=True,
            )
            self._jobs[session_id] = _ActiveUploadJob(thread=thread, cancel_event=cancel_event, started_at=started_at)
            session.status = "queued"
            self._write_session(session)
            self._mark_capability(
                "uploaded_video_pipeline",
                CapabilityState.ACTIVE,
                "Uploaded-video processing job queued.",
                {"session_id": session_id, "stage": "queued"},
                health_score=0.9,
            )
            status = UploadedVideoProcessingStatus(
                session_id=session_id,
                status="queued",
                progress=session.progress,
                started_at=started_at,
                active=True,
                report_ready=False,
                event_count=len(self.get_events(session_id, user)),
            )
            self._write_status(session_id, status)
            thread.start()
        _metric_increment("uploaded_video_processing_started_total")
        self._refresh_active_metric()
        return self.get_status(session_id, user)

    def get_session(self, session_id: str) -> UploadedVideoSession | None:
        path = self._session_path(session_id)
        payload = self._load_json_file(path, None)
        if payload is None:
            return None
        return UploadedVideoSession.model_validate(payload)

    def get_status(self, session_id: str, user: UserAccount | str | None = None) -> UploadedVideoProcessingStatus:
        del user
        path = self._status_path(session_id)
        payload = self._load_json_file(path, None)
        if payload is not None:
            return UploadedVideoProcessingStatus.model_validate(payload)
        session = self._require_session(session_id)
        return UploadedVideoProcessingStatus(
            session_id=session_id,
            status=session.status,
            progress=session.progress,
            completed_at=session.completed_at,
        )

    def get_timeline(self, session_id: str, user: UserAccount | str | None = None) -> list[UploadedVideoTimelineItem]:
        del user
        return [UploadedVideoTimelineItem.model_validate(item) for item in self._read_json(self._timeline_path(session_id), [])]

    def get_events(self, session_id: str, user: UserAccount | str | None = None) -> list[UploadedVideoEvent]:
        del user
        return [UploadedVideoEvent.model_validate(item) for item in self._read_json(self._events_path(session_id), [])]

    def get_report(self, session_id: str, user: UserAccount | str | None = None) -> UploadedVideoReport | None:
        del user
        path = self._report_path(session_id)
        payload = self._load_json_file(path, None)
        if payload is None:
            return None
        return UploadedVideoReport.model_validate(payload)

    def get_command_center_links(self, session_id: str, user: UserAccount | str | None = None) -> dict[str, Any] | None:
        del user
        link = self._command_center_service.get_uploaded_video_link(session_id)
        return link.command_center_summary() if link is not None else None

    def list_sessions(self, *, created_by: str | None = None) -> list[UploadedVideoSession]:
        items: list[UploadedVideoSession] = []
        seen: set[str] = set()
        for path in sorted(self._processed_dir.glob("*/session.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                session = UploadedVideoSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if created_by and session.created_by != created_by:
                continue
            if session.session_id in seen:
                continue
            seen.add(session.session_id)
            items.append(session)
        return items

    def cancel_processing(self, session_id: str, user: UserAccount | str) -> UploadedVideoProcessingStatus:
        del user
        with self._lock:
            job = self._jobs.get(session_id)
            if job is not None:
                job.cancel_event.set()
        session = self._require_session(session_id)
        session.status = "cancelled"
        session.completed_at = _now_iso()
        self._write_session(session)
        status = UploadedVideoProcessingStatus(
            session_id=session_id,
            status="cancelled",
            progress=session.progress,
            started_at=self._jobs.get(session_id).started_at if session_id in self._jobs else None,
            completed_at=session.completed_at,
            active=False,
            report_ready=self._report_path(session_id).exists(),
            event_count=len(self.get_events(session_id)),
        )
        self._write_status(session_id, status)
        self._mark_capability(
            "uploaded_video_pipeline",
            CapabilityState.READY,
            "Uploaded-video processing was cancelled; pipeline remains ready for a new job.",
            {"session_id": session_id, "stage": "cancelled"},
            health_score=0.85,
        )
        self._refresh_active_metric()
        return status

    def create_case_from_session(
        self,
        session_id: str,
        request: UploadedVideoCaseCreationRequest | dict[str, Any],
        user: UserAccount | str,
    ):
        session = self._require_session(session_id)
        payload = request if isinstance(request, UploadedVideoCaseCreationRequest) else UploadedVideoCaseCreationRequest.model_validate(request or {})
        report = self.get_report(session_id, user)
        events = self.get_events(session_id, user)
        timeline = self.get_timeline(session_id, user)
        case = self._case_service.create_case(
            CaseCreateRequest(
                title=payload.title or f"Uploaded video analysis {session.original_filename}",
                description=payload.description or "Uploaded video requires operator review.",
                priority=payload.priority,
                severity=payload.severity,
                source_event_ids=[event.event_id for event in events],
                camera_ids=[f"uploaded:{session_id}"],
                track_ids=[track_id for event in events for track_id in event.track_ids],
                metadata={
                    "source_type": "uploaded_video",
                    "session_id": session_id,
                    "timeline_count": len(timeline),
                },
            ),
            actor=_safe_user_id(user),
        )
        evidence_ids: list[str] = []
        if payload.attach_source_video and bool(self._case_cfg.get("attach_source_video_as_evidence", True)):
            evidence = self._case_service.add_evidence(
                case.case_id,
                CaseEvidenceCreateRequest(
                    evidence_type="upload",
                    title=f"Source video: {session.original_filename}",
                    description="Uploaded source video used for analysis.",
                    storage_uri=session.storage_uri,
                    original_filename=session.original_filename,
                    safe_filename=session.safe_filename,
                    content_type=str((session.metadata or {}).get("content_type") or mimetypes.guess_type(session.safe_filename)[0] or "video/mp4"),
                    size_bytes=int((session.metadata or {}).get("size_bytes") or 0) or None,
                    hash_sha256=session.hash_sha256,
                    hash_verified=True,
                    integrity_status="verified",
                    metadata={"source_type": "uploaded_video", "session_id": session_id},
                ),
                actor=_safe_user_id(user),
            )
            evidence_ids.append(evidence.evidence_id)
        if payload.attach_snapshots and bool(self._case_cfg.get("attach_snapshots_as_evidence", True)):
            for event in events:
                if not event.snapshot_uri:
                    continue
                evidence = self._case_service.add_evidence(
                    case.case_id,
                    CaseEvidenceCreateRequest(
                        evidence_type="image",
                        title=f"Snapshot: {event.event_type}",
                        description=event.summary or "Uploaded-video event snapshot.",
                        source_event_id=event.event_id,
                        storage_uri=event.snapshot_uri,
                        snapshot_uri=event.snapshot_uri,
                        hash_verified=True,
                        integrity_status="verified",
                        metadata={
                            "source_type": "uploaded_video",
                            "session_id": session_id,
                            "time_offset_seconds": event.time_offset_seconds,
                            "frame_index": event.frame_index,
                        },
                    ),
                    actor=_safe_user_id(user),
                )
                evidence_ids.append(evidence.evidence_id)
        if payload.attach_report and report is not None:
            report_path = self._report_path(session_id)
            evidence = self._case_service.add_evidence(
                case.case_id,
                CaseEvidenceCreateRequest(
                    evidence_type="system_report",
                    title=f"Uploaded video report: {session.original_filename}",
                    description="Generated uploaded-video analysis report.",
                    storage_uri=self._storage_uri(report_path),
                    hash_verified=True,
                    integrity_status="verified",
                    metadata={
                        "source_type": "uploaded_video",
                        "session_id": session_id,
                        "model_caveats": report.model_caveats,
                    },
                ),
                actor=_safe_user_id(user),
            )
            evidence_ids.append(evidence.evidence_id)
        attach_clips = bool(payload.attach_replay_clips) and bool(self._replay_cfg.get("attach_clips_as_evidence", True))
        if attach_clips:
            for event in events:
                clip = event.replay_clip
                if clip is None:
                    continue
                evidence = self._case_service.add_evidence(
                    case.case_id,
                    CaseEvidenceCreateRequest(
                        evidence_type="clip",
                        title=f"Uploaded-video event clip ({event.event_type})",
                        description=(
                            "Possible incident — operator review required. "
                            "Uploaded-video event clip; not proof of identity or criminality."
                        ),
                        source_event_id=event.event_id,
                        storage_uri=clip.storage_uri,
                        original_filename=f"{_safe_uploaded_video_event_filename(event.event_id)}.mp4",
                        safe_filename=f"{_safe_uploaded_video_event_filename(event.event_id)}.mp4",
                        content_type=clip.content_type,
                        size_bytes=int(clip.size_bytes or 0) or None,
                        hash_sha256=clip.hash_sha256,
                        hash_verified=True,
                        integrity_status="verified",
                        metadata={
                            "source_type": "uploaded_video",
                            "session_id": session_id,
                            "clip_id": clip.clip_id,
                            "event_id": event.event_id,
                            "export_type": "uploaded_video_replay",
                            "time_offset_seconds": event.time_offset_seconds,
                        },
                    ),
                    actor=_safe_user_id(user),
                )
                evidence_ids.append(evidence.evidence_id)
        session.linked_case_id = case.case_id
        existing_command_center = dict(session.metadata.get("command_center") or {}) if isinstance(session.metadata, dict) else {}
        linked = self._command_center_service.link_case_to_uploaded_video(session_id, case.case_id, evidence_ids)
        session.metadata = {
            **(session.metadata or {}),
            "command_center": linked.command_center_summary() if linked is not None else existing_command_center,
        }
        self._write_session(session)
        return case

    def health(self) -> dict[str, Any]:
        summary = self._progress_service.summary()
        replay_enabled = bool(self._replay_cfg.get("enabled", False))
        ffmpeg_ok = is_ffmpeg_available()
        if not replay_enabled:
            clip_status = "disabled"
        elif not ffmpeg_ok:
            clip_status = "degraded"
        else:
            clip_status = "healthy"
        return {
            "enabled": self.enabled,
            "status": "healthy" if self.enabled else "disabled",
            "active_sessions": summary["active_sessions"],
            "completed_sessions": summary["completed_sessions"],
            "failed_sessions": summary["failed_sessions"],
            "storage": "filesystem",
            "last_error": None,
            "replay_enabled": replay_enabled,
            "ffmpeg_available": ffmpeg_ok,
            "clip_generation_status": clip_status,
        }

    def resolve_event_clip_path(self, session_id: str, event_id: str) -> Path:
        """Resolve a replay clip path under managed uploaded-video results (no arbitrary paths)."""
        if not session_id or not event_id:
            raise ValueError("session_id and event_id are required")
        session_root = (self._processed_dir / session_id).resolve()
        if not session_root.is_dir():
            raise FileNotFoundError(session_id)
        safe = _safe_uploaded_video_event_filename(event_id)
        clip_path = (session_root / "clips" / f"{safe}.mp4").resolve()
        clips_root = (session_root / "clips").resolve()
        if clip_path.parent.resolve() != clips_root:
            raise ValueError("clip path escapes session clips directory")
        return clip_path

    def _sync_timeline_replay_clips(
        self,
        timeline: list[UploadedVideoTimelineItem],
        events: list[UploadedVideoEvent],
    ) -> None:
        by_id = {e.event_id: e for e in events}
        for item in timeline:
            ev = by_id.get(item.event_id or "")
            if ev and ev.replay_clip is not None:
                item.replay_clip = ev.replay_clip

    def _maybe_generate_uploaded_video_replay_clips(
        self,
        session: UploadedVideoSession,
        events: list[UploadedVideoEvent],
        timeline: list[UploadedVideoTimelineItem],
        source_video_path: Path,
        video_duration_seconds: float,
    ) -> None:
        if not bool(self._replay_cfg.get("enabled", False)):
            return
        if not events:
            return
        before = float(self._replay_cfg.get("clip_seconds_before", 10))
        after = float(self._replay_cfg.get("clip_seconds_after", 20))
        compute_hash = bool(self._replay_cfg.get("compute_sha256", True))
        clips_dir = self._session_dir(session.session_id) / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        if not is_ffmpeg_available():
            _metric_increment("uploaded_video_replay_clip_failures_total", len(events))
            return

        duration_cap = max(float(video_duration_seconds or 0.0), 0.1)
        for event in events:
            offset = float(event.time_offset_seconds or 0.0)
            safe = _safe_uploaded_video_event_filename(event.event_id)
            out_path = clips_dir / f"{safe}.mp4"
            try:
                raw = generate_uploaded_video_event_clip_ffmpeg(
                    source_video_path=source_video_path,
                    output_mp4_path=out_path,
                    session_id=session.session_id,
                    event_id=event.event_id,
                    event_offset_seconds=offset,
                    clip_seconds_before=before,
                    clip_seconds_after=after,
                    video_duration_seconds=max(duration_cap, offset + 0.05),
                    hash_output=compute_hash,
                )
                raw["storage_uri"] = self._storage_uri(out_path)
                event.replay_clip = UploadedVideoReplayClipMetadata.model_validate(raw)
                self._incident_repository.merge_event_metadata(
                    event.event_id,
                    {
                        "uploaded_video_replay_clip": {
                            "clip_id": event.replay_clip.clip_id,
                            "hash_sha256": event.replay_clip.hash_sha256,
                            "storage_uri": event.replay_clip.storage_uri,
                            "event_id": event.event_id,
                            "session_id": session.session_id,
                        },
                    },
                )
            except UploadedVideoReplayClipError:
                continue

        self._sync_timeline_replay_clips(timeline, events)

    def _process_session_job(self, session_id: str, cancel_event: threading.Event) -> None:
        session = self._require_session(session_id)
        started_at = _now_iso()
        self._write_processing_status(
            session,
            "processing",
            started_at=started_at,
            active=True,
            report_ready=False,
            event_count=0,
        )
        self._mark_capability(
            "uploaded_video_pipeline",
            CapabilityState.ACTIVE,
            "Uploaded-video processing job is active.",
            {"session_id": session_id, "stage": "processing"},
            health_score=0.95,
        )
        start_ts = time.monotonic()
        capture: cv2.VideoCapture | None = None
        generated_events: list[UploadedVideoEvent] = []
        generated_timeline: list[UploadedVideoTimelineItem] = []
        processed_frames = 0
        source_video_path = self._resolve_storage_uri(session.storage_uri)
        try:
            self._write_processing_status(
                session,
                "frame_extraction",
                started_at=started_at,
                active=True,
                report_ready=False,
                event_count=0,
            )
            model_pool = self._load_shared_model_pool(session)
            self._mark_capability(
                "tracking_engine",
                CapabilityState.ACTIVE,
                "Tracking engine engaged by uploaded-video processing.",
                {"session_id": session_id},
                health_score=0.9,
            )
            self._mark_capability(
                "event_engine",
                CapabilityState.ACTIVE,
                "Event engine engaged by uploaded-video processing.",
                {"session_id": session_id},
                health_score=0.9,
            )
            try:
                processor = StreamProcessor(
                    f"uploaded:{session_id}",
                    session.storage_uri,
                    model_pool,
                    enable_advanced_runtime=False,
                )
            except TypeError:
                processor = StreamProcessor(f"uploaded:{session_id}", session.storage_uri, model_pool)
            capture = cv2.VideoCapture(str(source_video_path))
            if not capture.isOpened():
                raise RuntimeError(f"OpenCV could not open uploaded video: {session.storage_uri}")
            total_frames = max(0, int(session.frame_count or capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
            fps = float(session.fps or capture.get(cv2.CAP_PROP_FPS) or 0.0) or 1.0
            stride = self._effective_stride(fps)
            target_max = self._processing_cfg.get("max_frames")
            if target_max is None:
                target_max = (session.metadata or {}).get("options", {}).get("max_frames")
            self._write_processing_status(
                session,
                "inference",
                started_at=started_at,
                active=True,
                report_ready=False,
                event_count=0,
            )
            frame_index = 0
            while True:
                if cancel_event.is_set():
                    session.status = "cancelled"
                    break
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                if frame_index % stride != 0:
                    frame_index += 1
                    continue
                if target_max is not None and processed_frames >= int(target_max):
                    break
                timestamp = _now_iso()
                offset_seconds = float(frame_index / max(fps, 1.0))
                packet = DecodedFramePacket(
                    camera_id=f"uploaded:{session_id}",
                    frame=frame,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    source_timestamp=timestamp,
                    width=int(frame.shape[1]),
                    height=int(frame.shape[0]),
                    fps_estimate=float(fps),
                    metadata={"source_type": "uploaded_video", "session_id": session_id},
                )
                result = processor.process_decoded_packet(packet)
                snapshot_uri = None
                if bool(self._processing_cfg.get("generate_snapshots", True)):
                    snapshot_uri = self._maybe_snapshot(session_id, frame_index, frame, result)
                frame_events = self._events_from_result(
                    session=session,
                    frame_index=frame_index,
                    offset_seconds=offset_seconds,
                    timestamp=timestamp,
                    result=result,
                    snapshot_uri=snapshot_uri,
                )
                if frame_events:
                    generated_events.extend(frame_events)
                    generated_timeline.extend(self._timeline_from_events(session_id, frame_events))
                    for event in frame_events:
                        self._incident_repository.append_event(
                            IncidentEventRecord(
                                incident_id=event.event_id,
                                event_id=event.event_id,
                                source_type="uploaded_video",
                                camera_id=f"uploaded:{session_id}",
                                session_id=session_id,
                                case_id=session.linked_case_id,
                                event_type=event.event_type,
                                severity=event.severity,
                                risk_score=event.risk_score,
                                timestamp=event.timestamp,
                                frame_index=event.frame_index,
                                time_offset_seconds=event.time_offset_seconds,
                                track_ids=event.track_ids,
                                object_refs=event.track_ids,
                                identity_ids=[],
                                summary=event.summary,
                                metadata=event.metadata,
                            )
                        )
                processed_frames += 1
                session.progress = UploadedVideoProgress(
                    frames_processed=processed_frames,
                    total_frames=total_frames or processed_frames,
                    percent=round((processed_frames / max(1, total_frames or processed_frames)) * 100.0, 2),
                )
                self._write_session(session)
                self._write_status(
                    session_id,
                    UploadedVideoProcessingStatus(
                        session_id=session_id,
                        status="inference",
                        progress=session.progress,
                        started_at=started_at,
                        active=True,
                        report_ready=False,
                        event_count=len(generated_events),
                    ),
                )
                _metric_increment("uploaded_video_frames_processed_total")
                frame_index += 1
            was_cancelled = session.status == "cancelled" or cancel_event.is_set()
            if not was_cancelled:
                self._write_processing_status(
                    session,
                    "event_generation",
                    started_at=started_at,
                    active=True,
                    report_ready=False,
                    event_count=len(generated_events),
                )
            session.completed_at = _now_iso()
            if not was_cancelled:
                session.status = "completed"
                _metric_increment("uploaded_video_processing_completed_total")
                get_audit_log_service().record(
                    AuditAction.UPLOADED_VIDEO_PROCESSING_COMPLETED,
                    resource_type="uploaded_video",
                    resource_id=session_id,
                    detail="Uploaded-video processing completed.",
                    metadata={"event_count": len(generated_events)},
                )
                video_duration_cap = float(session.duration_seconds or 0.0)
                if video_duration_cap <= 0.0:
                    video_duration_cap = float(self._video_metadata(source_video_path).get("duration_seconds") or 0.0)
                self._maybe_generate_uploaded_video_replay_clips(
                    session,
                    generated_events,
                    generated_timeline,
                    source_video_path,
                    video_duration_cap,
                )
                self._write_processing_status(
                    session,
                    "report_generation",
                    started_at=started_at,
                    active=True,
                    report_ready=False,
                    event_count=len(generated_events),
                )
            report = self._build_report(session, generated_events, generated_timeline, processed_frames, time.monotonic() - start_ts)
            session.report_uri = self._storage_uri(self._report_path(session_id))
            promotion = self._command_center_service.promote_uploaded_video(
                session=session,
                report=report,
                events=generated_events,
                timeline=generated_timeline,
            )
            report.metadata = {
                **(report.metadata or {}),
                "command_center": promotion.command_center_summary(),
            }
            report.chain_of_custody = {
                **(report.chain_of_custody or {}),
                "command_center_evidence_refs": list(promotion.evidence_refs),
                "normalized_intelligence_events": self._storage_uri(self._session_dir(session_id) / "normalized_intelligence_events.json"),
                "evidence_manifest": self._storage_uri(self._session_dir(session_id) / "evidence_manifest.json"),
            }
            session.metadata = {
                **(session.metadata or {}),
                "command_center": promotion.command_center_summary(),
            }
            self._write_json(self._events_path(session_id), [event.model_dump(mode="json") for event in generated_events])
            self._write_json(self._timeline_path(session_id), [item.model_dump(mode="json") for item in generated_timeline])
            self._write_json(self._report_path(session_id), report.model_dump(mode="json"))
            session.status = "cancelled" if was_cancelled else "completed"
            self._write_session(session)
            self._write_status(
                session_id,
                UploadedVideoProcessingStatus(
                    session_id=session_id,
                    status=session.status,
                    progress=session.progress,
                    started_at=started_at,
                    completed_at=session.completed_at,
                    active=False,
                    report_ready=True,
                    event_count=len(generated_events),
                ),
            )
            _metric_increment("uploaded_video_events_generated_total", len(generated_events))
            _metric_set("uploaded_video_processing_latency_ms", int((time.monotonic() - start_ts) * 1000))
            terminal_reason = (
                "Uploaded-video intelligence job completed and report is ready."
                if session.status == "completed"
                else "Uploaded-video processing cancelled before completion."
            )
            self._mark_capability(
                "uploaded_video_pipeline",
                CapabilityState.READY,
                terminal_reason,
                {"session_id": session_id, "event_count": len(generated_events), "frames_processed": processed_frames},
                health_score=0.95 if session.status == "completed" else 0.85,
            )
            for capability_id in ("tracking_engine", "event_engine"):
                self._mark_capability(
                    capability_id,
                    CapabilityState.READY,
                    "Runtime stage completed for uploaded-video processing.",
                    {"session_id": session_id},
                    health_score=0.9,
                )
        except Exception as exc:
            session.status = "failed"
            session.completed_at = _now_iso()
            self._write_processing_status(
                session,
                "failed",
                started_at=started_at,
                active=False,
                report_ready=self._report_path(session_id).exists(),
                event_count=len(generated_events),
                last_error=str(exc),
            )
            self._mark_capability_faulted(
                "uploaded_video_pipeline",
                exc,
                {"session_id": session_id, "stage": session.status, "event_count": len(generated_events)},
            )
            for capability_id in ("tracking_engine", "event_engine"):
                self._mark_capability(
                    capability_id,
                    CapabilityState.DEGRADED,
                    "Uploaded-video processing failed before the runtime stage completed.",
                    {"session_id": session_id, "error": str(exc)[:240]},
                    health_score=0.45,
                )
            _metric_increment("uploaded_video_processing_failed_total")
            get_audit_log_service().record(
                AuditAction.UPLOADED_VIDEO_PROCESSING_FAILED,
                resource_type="uploaded_video",
                resource_id=session_id,
                success=False,
                detail=f"Uploaded-video processing failed: {exc}",
            )
        finally:
            if capture is not None:
                capture.release()
            with self._lock:
                self._jobs.pop(session_id, None)
            self._refresh_active_metric()

    def _build_report(
        self,
        session: UploadedVideoSession,
        events: list[UploadedVideoEvent],
        timeline: list[UploadedVideoTimelineItem],
        processed_frames: int,
        elapsed_seconds: float,
    ) -> UploadedVideoReport:
        from ml.runtime.model_registry import get_model_registry

        active_models = get_model_registry().get_active_models()
        relevant_tasks = {"weapon_detection", "phone_detection", "face_embedding"}
        models_used = [item for item in active_models if str(item.get("task") or "") in relevant_tasks]
        counts_by_type: dict[str, int] = {}
        confidences: list[float] = []
        for event in events:
            counts_by_type[event.event_type] = counts_by_type.get(event.event_type, 0) + 1
            confidence = (event.metadata or {}).get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        confidence_summary = {
            "min": round(min(confidences), 4) if confidences else 0.0,
            "max": round(max(confidences), 4) if confidences else 0.0,
            "average": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "count": len(confidences),
        }
        replay_clips_payload: list[dict[str, Any]] = []
        coc_clips: list[dict[str, Any]] = []
        for event in events:
            if event.replay_clip is None:
                continue
            clip_dump = event.replay_clip.model_dump(mode="json")
            replay_clips_payload.append(clip_dump)
            coc_clips.append(
                {
                    "event_id": event.event_id,
                    "clip_id": event.replay_clip.clip_id,
                    "hash_sha256": event.replay_clip.hash_sha256,
                    "storage_uri": event.replay_clip.storage_uri,
                }
            )
        replay_summary = {
            "clips_generated": len(replay_clips_payload),
            "events_total": len(events),
            "events_with_clips": sum(1 for event in events if event.replay_clip is not None),
            "events_without_clips": sum(1 for event in events if event.replay_clip is None),
        }
        return UploadedVideoReport(
            session_id=session.session_id,
            generated_by=session.created_by,
            video_metadata={
                "original_filename": session.original_filename,
                "safe_filename": session.safe_filename,
                "duration_seconds": session.duration_seconds,
                "frame_count": session.frame_count,
                "fps": session.fps,
                "frames_processed": processed_frames,
                "processing_latency_seconds": round(elapsed_seconds, 3),
            },
            integrity={
                "hash_sha256": session.hash_sha256,
                "storage_uri": session.storage_uri,
                "status": "verified",
            },
            processing_options=dict((session.metadata or {}).get("options") or {}),
            models_used=models_used,
            timeline=timeline,
            detections_summary={
                "event_types": counts_by_type,
                "detected_classes": sorted(counts_by_type),
                "detection_count": len(events),
                "total_events": len(events),
                "confidence_summary": confidence_summary,
            },
            anomaly_summary={"event_count": sum(1 for event in events if "anomaly" in event.event_type)},
            identity_summary={"summary": "Any identity-related outputs remain possible matches pending operator review."},
            segmentation_summary={"status": "best_effort"},
            chain_of_custody={
                "source_video": session.storage_uri,
                "report_artifact": self._storage_uri(self._report_path(session.session_id)),
                "generated_at": _now_iso(),
                "replay_clip_hashes": [item["hash_sha256"] for item in coc_clips if item.get("hash_sha256")],
                "replay_clip_manifest": coc_clips,
            },
            replay_clips=replay_clips_payload,
            replay_summary=replay_summary,
            model_caveats=[
                "Uploaded-video analytics are advisory and require operator review.",
                "Identity-related outputs must not be treated as confirmed identification without human validation.",
                "Absence of detections is not proof of absence.",
                "Replay clips are contextual aids only; absence of a clip does not imply absence of activity.",
            ],
            metadata={"source_type": "uploaded_video"},
        )

    def _events_from_result(
        self,
        *,
        session: UploadedVideoSession,
        frame_index: int,
        offset_seconds: float,
        timestamp: str,
        result: dict[str, Any],
        snapshot_uri: str | None,
    ) -> list[UploadedVideoEvent]:
        items: list[UploadedVideoEvent] = []
        for event in list(result.get("events") or []):
            payload = _coerce_model(event)
            event_type = str(payload.get("event_type") or payload.get("type") or "event").lower()
            severity = str(payload.get("severity") or payload.get("risk_level") or "medium").lower()
            risk_score = float(payload.get("risk_score") or payload.get("severity_score") or payload.get("confidence_score") or 0.0)
            summary = str(payload.get("summary") or payload.get("description") or event_type.replace("_", " "))
            track_ids = [str(item) for item in payload.get("track_ids", []) if str(item)]
            items.append(
                UploadedVideoEvent(
                    event_id=str(payload.get("event_id") or f"uve_{session.session_id}_{frame_index}_{len(items)}"),
                    session_id=session.session_id,
                    event_type=event_type,
                    severity=severity,
                    risk_score=risk_score,
                    timestamp=timestamp,
                    frame_index=frame_index,
                    time_offset_seconds=round(offset_seconds, 3),
                    camera_ids=[f"uploaded:{session.session_id}"],
                    track_ids=track_ids,
                    snapshot_uri=snapshot_uri,
                    summary=summary,
                    metadata={
                        "source_type": "uploaded_video",
                        "session_id": session.session_id,
                        "frame_index": frame_index,
                        "time_offset_seconds": round(offset_seconds, 3),
                        "confidence": float(payload.get("confidence_score") or payload.get("confidence") or 0.0),
                    },
                )
            )
        return items

    def _timeline_from_events(self, session_id: str, events: list[UploadedVideoEvent]) -> list[UploadedVideoTimelineItem]:
        items: list[UploadedVideoTimelineItem] = []
        for event in events:
            items.append(
                UploadedVideoTimelineItem(
                    session_id=session_id,
                    event_id=event.event_id,
                    timestamp=event.timestamp,
                    time_offset_seconds=float(event.time_offset_seconds or 0.0),
                    frame_index=event.frame_index,
                    title=event.event_type.replace("_", " ").title(),
                    description=event.summary,
                    severity=event.severity,
                    snapshot_uri=event.snapshot_uri,
                    metadata=event.metadata,
                )
            )
        return items

    def _maybe_snapshot(
        self,
        session_id: str,
        frame_index: int,
        frame: Any,
        result: dict[str, Any],
    ) -> str | None:
        if not result.get("events"):
            return None
        snapshot_dir = self._session_dir(session_id) / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"frame_{frame_index:06d}.jpg"
        cv2.imwrite(str(snapshot_path), frame)
        return self._storage_uri(snapshot_path)

    def _effective_stride(self, fps: float) -> int:
        options_target_fps = int(self._processing_cfg.get("target_fps") or 15)
        base_stride = int(self._processing_cfg.get("frame_stride") or 1)
        if fps <= 0 or options_target_fps <= 0:
            return max(1, base_stride)
        adaptive_stride = max(1, round(fps / max(1, options_target_fps)))
        return max(1, adaptive_stride * base_stride)

    def _load_shared_model_pool(self, session: UploadedVideoSession) -> ModelPool:
        for capability_id in ("yolo_weapon_detector", "yolo_phone_detector"):
            self._mark_capability(
                capability_id,
                CapabilityState.WARMING,
                "Uploaded-video processing is validating and loading detector artifacts.",
                {"session_id": session.session_id},
                health_score=0.75,
            )

        router = ModelRouter()
        resolved_models: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        for task, capability_id in (
            ("weapon", "yolo_weapon_detector"),
            ("phone", "yolo_phone_detector"),
        ):
            try:
                resolved_models[task] = router.get_model(task)
            except Exception as exc:
                errors[capability_id] = str(exc)
                self._mark_capability_faulted(
                    capability_id,
                    exc,
                    {"session_id": session.session_id, "task": task},
                )

        if errors:
            details = "; ".join(f"{capability_id}: {message}" for capability_id, message in errors.items())
            raise RuntimeError(f"Detector capability not ready for uploaded-video processing. {details}")

        model_pool = ModelPool()
        options = (session.metadata or {}).get("options") or {}
        requested_device = str(
            options.get("device")
            or (options.get("metadata") or {}).get("requested_device")
            or self._processing_cfg.get("default_device")
            or "auto"
        )
        try:
            if not model_pool.is_loaded:
                model_pool.load(
                    str(resolved_models["weapon"]["resolved_path"]),
                    str(resolved_models["phone"]["resolved_path"]),
                    device=requested_device,
                )
            for task, capability_id in (
                ("weapon", "yolo_weapon_detector"),
                ("phone", "yolo_phone_detector"),
            ):
                resolved = resolved_models[task]
                self._mark_capability(
                    capability_id,
                    CapabilityState.READY,
                    "Detector model is loaded for uploaded-video processing.",
                    {
                        "session_id": session.session_id,
                        "model_id": resolved.get("model_id"),
                        "version": resolved.get("version") or resolved.get("selected_version"),
                        "device": getattr(model_pool, "device", requested_device),
                    },
                    health_score=0.95,
                )
            try:
                from ml.runtime.model_registry import get_model_registry

                registry = get_model_registry()
                for task in ("weapon", "phone"):
                    model_id = resolved_models[task].get("model_id")
                    if model_id:
                        registry.update_model_health(
                            str(model_id),
                            "loaded",
                            detail="Loaded by uploaded-video processing job.",
                            device=getattr(model_pool, "device", requested_device),
                        )
            except Exception:
                pass
        except Exception as exc:
            for capability_id in ("yolo_weapon_detector", "yolo_phone_detector"):
                self._mark_capability_faulted(
                    capability_id,
                    exc,
                    {"session_id": session.session_id, "device": requested_device},
                )
            raise RuntimeError(f"Detector model activation failed for uploaded-video processing: {exc}") from exc
        return model_pool

    def _video_metadata(self, path: Path) -> dict[str, Any]:
        capture = cv2.VideoCapture(str(path))
        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            duration = float(frame_count / fps) if fps > 0 and frame_count > 0 else 0.0
            return {"frame_count": frame_count, "fps": fps, "duration_seconds": duration}
        finally:
            capture.release()

    def _refresh_active_metric(self) -> None:
        with self._lock:
            active = sum(1 for job in self._jobs.values() if job.thread.is_alive())
        _metric_set("uploaded_video_active_sessions", active)

    def _write_session(self, session: UploadedVideoSession) -> None:
        self._write_json(self._session_path(session.session_id), session.model_dump(mode="json"))

    def _write_status(self, session_id: str, status: UploadedVideoProcessingStatus) -> None:
        self._write_json(self._status_path(session_id), status.model_dump(mode="json"))
        self._progress_service.update(status)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        for attempt in range(8):
            try:
                temp_path.replace(path)
                return
            except PermissionError:
                if attempt >= 7:
                    raise
                time.sleep(0.01 * (attempt + 1))

    def _read_json(self, path: Path, default: Any) -> Any:
        return self._load_json_file(path, default)

    def _load_json_file(self, path: Path, default: Any, *, retries: int = 3) -> Any:
        for attempt in range(max(1, retries)):
            if not path.exists():
                return default
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                if attempt >= retries - 1:
                    raise
                time.sleep(0.02)
        return default

    def _require_session(self, session_id: str) -> UploadedVideoSession:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def _session_dir(self, session_id: str) -> Path:
        path = (self._processed_dir / session_id).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _session_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "session.json"

    def _status_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "status.json"

    def _events_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "events.json"

    def _timeline_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "timeline.json"

    def _report_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "report.json"

    def _storage_uri(self, path: Path) -> str:
        return str(path.resolve().relative_to(PROJECT_ROOT).as_posix())

    def _resolve_storage_uri(self, storage_uri: str) -> Path:
        return (PROJECT_ROOT / storage_uri).resolve()

    def _resolve_dir(self, relative_path: str) -> Path:
        path = (PROJECT_ROOT / relative_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


_UPLOADED_VIDEO_SERVICE: UploadedVideoService | None = None
_UPLOADED_VIDEO_LOCK = threading.Lock()


def get_uploaded_video_service() -> UploadedVideoService:
    global _UPLOADED_VIDEO_SERVICE
    with _UPLOADED_VIDEO_LOCK:
        if _UPLOADED_VIDEO_SERVICE is None:
            _UPLOADED_VIDEO_SERVICE = UploadedVideoService()
        return _UPLOADED_VIDEO_SERVICE
