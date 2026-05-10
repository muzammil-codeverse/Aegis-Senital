from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2

from app.models.streaming_models import ReplayClipRequest, ReplayClipResponse
from app.services.case_service import get_case_service
from app.services.evidence_integrity import compute_sha256
from app.services.rtsp_ingest_service import load_streaming_runtime_config
from app.services.stream_session_manager import get_stream_session_manager

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(timezone.utc)
    except ValueError:
        return None


def _severity_rank(value: str | None) -> int:
    order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return order.get(str(value or "").lower(), 0)


def _safe_camera_component(camera_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(camera_id or "").strip())
    return cleaned or "camera"


class ReplayClipService:
    def __init__(self) -> None:
        self._config = load_streaming_runtime_config().get("streaming", {})
        self._replay_cfg = self._config.get("replay", {})
        self._case_cfg = self._config.get("case_integration", {})
        self._enabled = bool(self._config.get("enabled", True)) and bool(self._replay_cfg.get("enabled", False))
        self._output_dir = Path(str(self._replay_cfg.get("output_dir") or "storage/replay"))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._default_before = int(self._replay_cfg.get("evidence_clip_seconds_before", 10))
        self._default_after = int(self._replay_cfg.get("evidence_clip_seconds_after", 20))
        self._hash_enabled = bool(self._replay_cfg.get("include_sha256", False))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def export_clip(self, camera_id: str, payload: ReplayClipRequest | dict, actor: str = "system") -> ReplayClipResponse:
        request = payload if isinstance(payload, ReplayClipRequest) else ReplayClipRequest.model_validate(payload)
        if not self._enabled:
            return ReplayClipResponse(
                clip_id=self._clip_id(),
                camera_id=camera_id,
                status="disabled",
                detail="replay export is disabled by runtime configuration",
            )

        source_uri, source_type, stats = self._resolve_source(camera_id)
        if not source_uri:
            return ReplayClipResponse(
                clip_id=self._clip_id(),
                camera_id=camera_id,
                status="unavailable",
                detail="camera source is unavailable",
            )

        clip_start_at, clip_end_at = self._resolve_window(camera_id, request, stats)
        if clip_start_at is None or clip_end_at is None:
            return ReplayClipResponse(
                clip_id=self._clip_id(),
                camera_id=camera_id,
                status="unavailable",
                detail="unable to resolve replay time window",
            )

        if source_type != "file":
            return ReplayClipResponse(
                clip_id=self._clip_id(),
                camera_id=camera_id,
                status="unavailable",
                detail="replay export currently supports file-backed sources only",
            )

        clip_id = self._clip_id()
        camera_dir = self._camera_dir(camera_id)
        camera_dir.mkdir(parents=True, exist_ok=True)
        clip_path = camera_dir / f"{clip_id}.mp4"
        metadata_path = camera_dir / f"{clip_id}.json"
        source_base_timestamp = _parse_iso(stats.get("source_base_timestamp"))
        if source_base_timestamp is None:
            source_base_timestamp = _parse_iso(stats.get("last_source_timestamp")) or _parse_iso(stats.get("last_frame_at"))
        export_meta = self._export_from_file(
            Path(source_uri),
            clip_path,
            source_base_timestamp,
            clip_start_at,
            clip_end_at,
        )
        export_meta.update(
            {
                "clip_id": clip_id,
                "camera_id": camera_id,
                "created_at": _now_iso(),
                "source_type": source_type,
                "source_uri": source_uri,
                "request": request.model_dump(mode="json"),
                "clip_start_at": clip_start_at.isoformat(),
                "clip_end_at": clip_end_at.isoformat(),
            }
        )
        metadata_path.write_text(json.dumps(export_meta, indent=2), encoding="utf-8")
        self._increment_metric("stream_replay_clips_created_total")

        digest = compute_sha256(str(clip_path)) if (self._hash_enabled or request.include_hash) else None
        attached_case_id = None
        if request.case_id and self._should_attach_to_case(request):
            attached_case_id = self._attach_to_case(
                request.case_id,
                camera_id,
                clip_path,
                digest,
                clip_start_at,
                clip_end_at,
                actor=actor,
                clip_id=clip_id,
            )

        return ReplayClipResponse(
            clip_id=clip_id,
            camera_id=camera_id,
            status="ready",
            file_path=str(clip_path),
            metadata_path=str(metadata_path),
            download_url=f"/api/streams/{camera_id}/replay/{clip_id}",
            hash_sha256=digest,
            attached_case_id=attached_case_id,
        )

    def resolve_clip_path(self, camera_id: str, clip_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(clip_id or "")):
            raise ValueError("unsafe clip identifier")
        clip_path = (self._camera_dir(camera_id) / f"{clip_id}.mp4").resolve()
        base = self._camera_dir(camera_id).resolve()
        if base not in clip_path.parents:
            raise ValueError("clip path escapes replay directory")
        return clip_path

    def resolve_metadata_path(self, camera_id: str, clip_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(clip_id or "")):
            raise ValueError("unsafe clip identifier")
        metadata_path = (self._camera_dir(camera_id) / f"{clip_id}.json").resolve()
        base = self._camera_dir(camera_id).resolve()
        if base not in metadata_path.parents:
            raise ValueError("clip metadata path escapes replay directory")
        return metadata_path

    def _resolve_source(self, camera_id: str) -> tuple[str | None, str | None, dict]:
        stats = get_stream_session_manager().get_stream_stats(camera_id)
        processor = get_stream_session_manager().get_stream_processor(camera_id)
        source_uri = getattr(processor, "source", None)
        source_type = getattr(processor, "source_type", None)
        if source_uri:
            return str(source_uri), str(source_type or stats.get("source_type") or "file"), stats
        try:
            from app.services.camera_registry import get_camera_registry

            camera = get_camera_registry().get_camera(camera_id)
        except Exception:
            camera = None
        return (camera.source_uri if camera else None), (camera.source_type if camera else None), stats

    def _resolve_window(self, camera_id: str, request: ReplayClipRequest, stats: dict) -> tuple[datetime | None, datetime | None]:
        direct_start = _parse_iso(request.start_at)
        direct_end = _parse_iso(request.end_at)
        if direct_start and direct_end:
            return direct_start, direct_end

        center = self._resolve_center_timestamp(camera_id, request, stats)
        if center is None:
            return None, None
        before_seconds = int(request.seconds_before or self._default_before)
        after_seconds = int(request.seconds_after or self._default_after)
        return center - timedelta(seconds=before_seconds), center + timedelta(seconds=after_seconds)

    def _resolve_center_timestamp(self, camera_id: str, request: ReplayClipRequest, stats: dict) -> datetime | None:
        if request.event_id:
            try:
                payload = get_case_service().resolve_event_by_id(request.event_id)
            except Exception:
                payload = None
            if payload is not None:
                source = payload.get("payload") or payload
                timestamp = source.get("timestamp") or source.get("scan_timestamp") or source.get("created_at")
                parsed = _parse_iso(timestamp)
                if parsed is not None:
                    return parsed
        if request.case_id:
            try:
                evidence = get_case_service().list_evidence(request.case_id)
            except Exception:
                evidence = []
            if evidence:
                parsed = _parse_iso(evidence[-1].timestamp)
                if parsed is not None:
                    return parsed
        parsed = _parse_iso(stats.get("last_source_timestamp")) or _parse_iso(stats.get("last_frame_at"))
        if parsed is not None:
            return parsed
        return datetime.now(timezone.utc)

    def _export_from_file(
        self,
        source_path: Path,
        clip_path: Path,
        source_base_timestamp: datetime | None,
        clip_start_at: datetime,
        clip_end_at: datetime,
    ) -> dict:
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            raise RuntimeError(f"unable to open source file: {source_path}")
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 15.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_seconds = (total_frames / fps) if fps > 0 and total_frames > 0 else None

            base_timestamp = source_base_timestamp or clip_start_at
            start_offset = max(0.0, (clip_start_at - base_timestamp).total_seconds())
            end_offset = max(start_offset, (clip_end_at - base_timestamp).total_seconds())
            if duration_seconds is not None:
                start_offset = min(start_offset, duration_seconds)
                end_offset = min(end_offset, duration_seconds)
            if end_offset <= start_offset:
                end_offset = start_offset + max(1.0 / fps, 0.2)

            start_frame = int(start_offset * fps)
            end_frame = max(start_frame, int(end_offset * fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            writer = cv2.VideoWriter(
                str(clip_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (width, height),
            )
            if not writer.isOpened():
                raise RuntimeError(f"unable to create clip writer: {clip_path}")
            frames_written = 0
            current_frame = start_frame
            try:
                while current_frame <= end_frame:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    writer.write(frame)
                    frames_written += 1
                    current_frame += 1
            finally:
                writer.release()
            if frames_written <= 0:
                raise RuntimeError("no frames were written to the replay clip")

            return {
                "frames_written": frames_written,
                "fps": fps,
                "frame_width": width,
                "frame_height": height,
                "source_total_frames": total_frames,
                "source_duration_seconds": duration_seconds,
                "clip_start_offset_seconds": round(start_offset, 3),
                "clip_end_offset_seconds": round(end_offset, 3),
            }
        finally:
            cap.release()

    def _attach_to_case(
        self,
        case_id: str,
        camera_id: str,
        clip_path: Path,
        digest: str | None,
        clip_start_at: datetime,
        clip_end_at: datetime,
        *,
        actor: str,
        clip_id: str,
    ) -> str:
        service = get_case_service()
        service.add_evidence(
            case_id,
            {
                "evidence_type": "clip",
                "title": f"Replay clip for {camera_id}",
                "description": "Operator-requested replay clip export.",
                "camera_id": camera_id,
                "storage_uri": str(clip_path),
                "timestamp": clip_start_at.isoformat(),
                "metadata": {
                    "clip_id": clip_id,
                    "clip_end_at": clip_end_at.isoformat(),
                    "hash_sha256": digest,
                },
            },
            actor=actor,
        )
        return case_id

    def _should_attach_to_case(self, request: ReplayClipRequest) -> bool:
        if request.attach_to_case:
            return True
        if not self._case_cfg.get("auto_attach_replay_for_high_risk", False):
            return False
        return _severity_rank(request.severity) >= _severity_rank(self._case_cfg.get("min_severity", "high"))

    def _clip_id(self) -> str:
        return f"clip_{uuid.uuid4().hex[:12]}"

    def _camera_dir(self, camera_id: str) -> Path:
        return self._output_dir / _safe_camera_component(camera_id)

    def _increment_metric(self, name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics

            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics

            metrics.increment(name, count)
        except Exception:
            pass


_replay_clip_service: ReplayClipService | None = None


def get_replay_clip_service() -> ReplayClipService:
    global _replay_clip_service
    if _replay_clip_service is None:
        _replay_clip_service = ReplayClipService()
    return _replay_clip_service
