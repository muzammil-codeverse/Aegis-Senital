from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.incident_models import IncidentEventRecord
from app.models.intelligence_models import (
    IntelligenceEvidenceArtifact,
    IntelligenceSourceType,
    NormalizedIntelligenceEvent,
    UploadedVideoPromotionRecord,
)
from app.models.uploaded_video_models import (
    UploadedVideoEvent,
    UploadedVideoReport,
    UploadedVideoSession,
    UploadedVideoTimelineItem,
)
from app.repositories.incident_repository import IncidentRepository, get_incident_repository
from app.security.config import PROJECT_ROOT
from app.services.case_service import CaseService, get_case_service


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
ACTIVE_ALERT_STATES = {"new", "dispatched", "acknowledged", "escalated"}
THREAT_EVENT_TYPES = {
    "weapon_detected",
    "phone_detected",
    "suspicious_person",
    "person_tracking",
    "zone_intrusion",
    "suspect_movement",
    "drone_observation",
    "camera_handoff",
    "scenario_incident",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch_from_iso(value: str | None) -> float:
    if not value:
        return time.time()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(value).strip()).strip("-").lower()[:96] or uuid.uuid4().hex[:12]


def _risk_score(confidence: float | None, severity: str, fallback: float = 0.0) -> float:
    severity_floor = {
        "critical": 0.9,
        "high": 0.72,
        "medium": 0.48,
        "low": 0.24,
        "info": 0.05,
    }.get(str(severity or "").lower(), 0.0)
    return round(max(float(confidence or 0.0), float(fallback or 0.0), severity_floor), 4)


def _detected_class(event_type: str, metadata: dict[str, Any]) -> str | None:
    explicit = metadata.get("detected_class") or metadata.get("class") or metadata.get("label")
    if explicit:
        return str(explicit)
    lowered = str(event_type or "").lower()
    if "weapon" in lowered:
        return "weapon"
    if "phone" in lowered:
        return "phone"
    if "person" in lowered or "suspect" in lowered:
        return "person"
    if "drone" in lowered:
        return "drone"
    return lowered or None


def _severity_for_event(event_type: str, confidence: float | None, risk_score: float | None, fallback: str = "medium") -> str:
    event_type = str(event_type or "").lower()
    confidence_value = float(confidence or 0.0)
    risk_value = float(risk_score or 0.0)
    fallback_value = str(fallback or "medium").lower()
    if event_type == "weapon_detected":
        return "critical" if max(confidence_value, risk_value) >= 0.9 else "high"
    if event_type == "phone_detected":
        return "medium" if max(confidence_value, risk_value) >= 0.75 else "low"
    if event_type in {"zone_intrusion", "suspect_movement", "scenario_incident"}:
        return "high" if max(confidence_value, risk_value) >= 0.75 else "medium"
    if event_type in {"suspicious_person", "person_tracking", "drone_observation", "camera_handoff"}:
        return "medium" if fallback_value not in {"high", "critical"} else fallback_value
    return fallback_value if fallback_value in SEVERITY_ORDER else "medium"


def _first_track_id(event: UploadedVideoEvent | dict[str, Any]) -> str | None:
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    track_ids = payload.get("track_ids") or []
    if isinstance(track_ids, list) and track_ids:
        return str(track_ids[0])
    if payload.get("track_id"):
        return str(payload["track_id"])
    return None


def _event_track_ids(event: UploadedVideoEvent | dict[str, Any]) -> list[str]:
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    track_ids = payload.get("track_ids") or []
    if not isinstance(track_ids, list):
        track_ids = [track_ids]
    return [str(item) for item in track_ids if str(item)]


def _relative_storage_uri(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_storage_uri(storage_uri: str | None) -> Path | None:
    if not storage_uri:
        return None
    path = Path(str(storage_uri))
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / storage_uri).resolve()


class UploadedVideoIntelligenceAdapter:
    def normalize(
        self,
        *,
        session: UploadedVideoSession,
        report: UploadedVideoReport | None,
        event: UploadedVideoEvent,
        timeline_item: UploadedVideoTimelineItem | None = None,
        evidence_refs: list[str] | None = None,
    ) -> NormalizedIntelligenceEvent:
        metadata = dict(event.metadata or {})
        confidence = metadata.get("confidence")
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else None
        event_type = str(event.event_type or "suspicious_person").lower()
        severity = _severity_for_event(event_type, confidence_value, event.risk_score, event.severity)
        timeline_ref = timeline_item.timeline_id if timeline_item else None
        return NormalizedIntelligenceEvent(
            event_id=event.event_id,
            source_type="uploaded_video",
            source_id=session.session_id,
            session_id=session.session_id,
            camera_id=f"uploaded:{session.session_id}",
            frame_index=event.frame_index,
            timestamp=event.timestamp,
            detected_class=_detected_class(event_type, metadata),
            confidence=confidence_value,
            bounding_box=metadata.get("bounding_box") or metadata.get("bbox"),
            track_id=_first_track_id(event),
            event_type=event_type,
            severity=severity,
            description=event.summary or event_type.replace("_", " "),
            evidence_refs=list(evidence_refs or []),
            metadata={
                **metadata,
                "source_type": "uploaded_video",
                "session_id": session.session_id,
                "report_id": report.report_id if report else None,
                "timeline_id": timeline_ref,
                "time_offset_seconds": event.time_offset_seconds,
                "risk_score": event.risk_score,
                "original_filename": session.original_filename,
                "snapshot_uri": event.snapshot_uri,
                "replay_clip": event.replay_clip.model_dump(mode="json") if event.replay_clip else None,
            },
        )


class SimulationObservationAdapter:
    def normalize_observation(self, observation: dict[str, Any]) -> NormalizedIntelligenceEvent:
        source_type = str(observation.get("source_type") or "simulation_cctv").lower()
        if source_type not in {"simulation_cctv", "drone_camera", "live_stream", "scenario_observation"}:
            raise ValueError(f"Unsupported simulation/drone observation source_type: {source_type}")
        metadata = dict(observation.get("metadata") or {})
        if source_type in {"simulation_cctv", "scenario_observation"}:
            metadata["simulated"] = bool(metadata.get("simulated", True))
        camera_id = observation.get("camera_id")
        drone_id = observation.get("drone_id")
        source_id = (
            observation.get("source_id")
            or camera_id
            or drone_id
            or observation.get("scenario_id")
            or observation.get("stream_id")
        )
        if not source_id:
            raise ValueError("Observation must include source_id, camera_id, drone_id, scenario_id, or stream_id")
        event_type = str(observation.get("event_type") or "suspicious_person").lower()
        confidence = observation.get("confidence")
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else None
        severity = _severity_for_event(event_type, confidence_value, observation.get("risk_score"), observation.get("severity") or "medium")
        return NormalizedIntelligenceEvent(
            event_id=str(observation.get("event_id") or f"nie_{_slug(source_type)}_{_slug(str(source_id))}_{uuid.uuid4().hex[:8]}"),
            source_type=source_type,  # type: ignore[arg-type]
            source_id=str(source_id),
            session_id=observation.get("session_id") or observation.get("scenario_id"),
            stream_id=observation.get("stream_id"),
            camera_id=str(camera_id) if camera_id else None,
            drone_id=str(drone_id) if drone_id else None,
            frame_index=observation.get("frame_index"),
            timestamp=str(observation.get("timestamp") or _now_iso()),
            zone=observation.get("zone") or metadata.get("zone"),
            location=observation.get("location"),
            detected_class=observation.get("detected_class"),
            confidence=confidence_value,
            bounding_box=observation.get("bounding_box") or observation.get("bbox"),
            track_id=str(observation.get("track_id")) if observation.get("track_id") is not None else None,
            event_type=event_type,
            severity=severity,
            description=str(observation.get("description") or event_type.replace("_", " ")),
            evidence_refs=[str(item) for item in observation.get("evidence_refs") or []],
            metadata={
                **metadata,
                "scenario_id": observation.get("scenario_id"),
                "risk_score": observation.get("risk_score"),
            },
        )


class CommandCenterIntelligenceService:
    def __init__(
        self,
        *,
        storage_dir: str | Path = "storage/command_center_intelligence",
        incident_repository: IncidentRepository | None = None,
        case_service: CaseService | None = None,
    ) -> None:
        self._storage_dir = Path(storage_dir)
        if not self._storage_dir.is_absolute():
            self._storage_dir = (PROJECT_ROOT / self._storage_dir).resolve()
        self._records_dir = self._storage_dir / "uploaded_video_promotions"
        self._records_dir.mkdir(parents=True, exist_ok=True)
        self._incident_repository = incident_repository or get_incident_repository()
        self._case_service = case_service or get_case_service()
        self._uploaded_video_adapter = UploadedVideoIntelligenceAdapter()
        self._simulation_adapter = SimulationObservationAdapter()
        self._lock = threading.RLock()

    @property
    def simulation_adapter(self) -> SimulationObservationAdapter:
        return self._simulation_adapter

    @property
    def uploaded_video_adapter(self) -> UploadedVideoIntelligenceAdapter:
        return self._uploaded_video_adapter

    def promote_uploaded_video(
        self,
        *,
        session: UploadedVideoSession,
        report: UploadedVideoReport | None,
        events: list[UploadedVideoEvent],
        timeline: list[UploadedVideoTimelineItem],
        dry_run: bool = False,
    ) -> UploadedVideoPromotionRecord:
        existing = self.get_uploaded_video_link(session.session_id)
        if existing is not None and not dry_run:
            return existing

        timeline_by_event = {item.event_id: item for item in timeline if item.event_id}
        evidence_artifacts = self._build_evidence_artifacts(session, report, events, dry_run=dry_run)
        evidence_refs = [item.evidence_ref for item in evidence_artifacts]
        normalized_events: list[NormalizedIntelligenceEvent] = []
        alerts: list[dict[str, Any]] = []
        incidents: list[dict[str, Any]] = []

        for event in events:
            event_refs = self._event_evidence_refs(event, evidence_refs)
            normalized = self._uploaded_video_adapter.normalize(
                session=session,
                report=report,
                event=event,
                timeline_item=timeline_by_event.get(event.event_id),
                evidence_refs=event_refs,
            )
            normalized_events.append(normalized)
            if not self._should_promote(normalized):
                continue
            incident = self._incident_from_event(session, normalized, report)
            alert = self._alert_from_event(session, normalized, incident, report)
            incident.setdefault("metadata", {})["alert_id"] = alert["alert_id"]
            incidents.append(incident)
            alerts.append(alert)

        status = "dry_run" if dry_run else ("promoted" if alerts else "no_detections")
        record = UploadedVideoPromotionRecord(
            session_id=session.session_id,
            report_id=report.report_id if report else None,
            status=status,
            normalized_events=normalized_events,
            alert_ids=[str(item["alert_id"]) for item in alerts],
            incident_ids=[str(item["incident_id"]) for item in incidents],
            evidence_refs=evidence_refs,
            evidence_artifacts=evidence_artifacts,
            alerts=alerts,
            incidents=incidents,
            alert_history=[
                {
                    "record_type": "alert",
                    "timestamp": alert["created_at"],
                    "alert_id": alert["alert_id"],
                    "alert": alert,
                }
                for alert in alerts
            ],
            analytics=self._analytics_payload(normalized_events, alerts, evidence_artifacts),
            metadata={
                "source_type": "uploaded_video",
                "original_filename": session.original_filename,
                "report_uri": session.report_uri,
                "dry_run": dry_run,
            },
        )
        if dry_run:
            return record

        self._persist_session_artifacts(session, record)
        for normalized, incident in zip(
            [item for item in normalized_events if self._should_promote(item)],
            incidents,
            strict=False,
        ):
            self._persist_incident_event(normalized, incident)
        self._write_record(record)
        return record

    def link_case_to_uploaded_video(self, session_id: str, case_id: str, evidence_ids: list[str] | None = None) -> UploadedVideoPromotionRecord | None:
        with self._lock:
            record = self.get_uploaded_video_link(session_id)
            if record is None:
                return None
            if case_id not in record.case_ids:
                record.case_ids.append(case_id)
            evidence_ids = list(evidence_ids or [])
            for artifact in record.evidence_artifacts:
                ids = artifact.metadata.setdefault("case_evidence_ids", [])
                for evidence_id in evidence_ids:
                    if evidence_id not in ids:
                        ids.append(evidence_id)
            for alert in record.alerts:
                alert.setdefault("metadata", {})["case_id"] = case_id
            for incident in record.incidents:
                incident["case_id"] = case_id
                incident.setdefault("metadata", {})["case_id"] = case_id
            for event in record.normalized_events:
                event.metadata["case_id"] = case_id
            self._write_record(record)
            return record

    def get_uploaded_video_link(self, session_id: str) -> UploadedVideoPromotionRecord | None:
        path = self._record_path(session_id)
        payload = self._read_json(path, None)
        return UploadedVideoPromotionRecord.model_validate(payload) if payload else None

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        for record in self._iter_records():
            for alert in record.alerts:
                if alert.get("alert_id") == alert_id:
                    return dict(alert)
        return None

    def list_alerts(
        self,
        *,
        state: str | None = None,
        severity: str | None = None,
        limit: int = 100,
        live_only: bool = False,
    ) -> list[dict[str, Any]]:
        state_filter = str(state).lower() if state else None
        severity_filter = str(severity).lower() if severity else None
        alerts: list[dict[str, Any]] = []
        for record in self._iter_records():
            for item in record.alerts:
                alert = dict(item)
                if live_only and str(alert.get("state") or "").lower() not in ACTIVE_ALERT_STATES:
                    continue
                if state_filter and str(alert.get("state") or "").lower() != state_filter:
                    continue
                if severity_filter and str(alert.get("severity") or "").lower() != severity_filter:
                    continue
                alerts.append(alert)
        alerts.sort(key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0.0), reverse=True)
        return alerts[: max(1, limit)]

    def transition_alert(
        self,
        alert_id: str,
        state: str,
        *,
        operator_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        target_state = str(state or "").lower()
        timestamp = time.time()
        with self._lock:
            for record in self._iter_records():
                changed = False
                for alert in record.alerts:
                    if alert.get("alert_id") != alert_id:
                        continue
                    previous = str(alert.get("state") or "new")
                    alert["state"] = target_state
                    alert["updated_at"] = timestamp
                    if target_state == "acknowledged":
                        alert["acknowledged_at"] = timestamp
                    elif target_state == "resolved":
                        alert["resolved_at"] = timestamp
                    elif target_state == "escalated":
                        alert["escalation_count"] = int(alert.get("escalation_count") or 0) + 1
                    transition = {
                        "record_type": "transition",
                        "timestamp": timestamp,
                        "alert_id": alert_id,
                        "from_state": previous,
                        "to_state": target_state,
                        "metadata": {"operator_id": operator_id, "reason": reason},
                    }
                    record.alert_history.append(transition)
                    changed = True
                    result = dict(alert)
                    break
                else:
                    result = None
                if changed:
                    self._write_record(record)
                    return result
        return None

    def get_alert_history(self, alert_id: str) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for record in self._iter_records():
            history.extend(item for item in record.alert_history if item.get("alert_id") == alert_id)
        history.sort(key=lambda item: float(item.get("timestamp") or 0.0))
        return history

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        for record in self._iter_records():
            for incident in record.incidents:
                if incident.get("incident_id") == incident_id or incident.get("id") == incident_id:
                    return dict(incident)
        return None

    def list_incidents(self, *, limit: int = 100) -> list[dict[str, Any]]:
        incidents: list[dict[str, Any]] = []
        for record in self._iter_records():
            incidents.extend(dict(item) for item in record.incidents)
        incidents.sort(key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0.0), reverse=True)
        return incidents[: max(1, limit)]

    def analytics_summary(self) -> dict[str, Any]:
        records = [record for record in self._iter_records() if record.status in {"promoted", "no_detections"}]
        normalized_events = [event for record in records for event in record.normalized_events]
        alerts = [alert for record in records for alert in record.alerts]
        evidence_artifacts = [artifact for record in records for artifact in record.evidence_artifacts]
        detections_by_class: dict[str, int] = {}
        events_by_source_type: dict[str, int] = {}
        confidences: list[float] = []
        high_severity = 0
        for event in normalized_events:
            key = event.detected_class or event.event_type
            detections_by_class[key] = detections_by_class.get(key, 0) + 1
            events_by_source_type[event.source_type] = events_by_source_type.get(event.source_type, 0) + 1
            if event.confidence is not None:
                confidences.append(float(event.confidence))
            if SEVERITY_ORDER.get(event.severity, 0) >= SEVERITY_ORDER["high"]:
                high_severity += 1
        return {
            "processed_videos": len(records),
            "detections_total": len(normalized_events),
            "detections_by_class": detections_by_class,
            "alerts_generated": len(alerts),
            "high_severity_detections": high_severity,
            "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "events_by_source_type": events_by_source_type,
            "evidence_artifacts_created": len(evidence_artifacts),
            "recent_alerts": self.list_alerts(limit=5),
            "recent_incidents": self.list_incidents(limit=5),
        }

    def health(self, *, dry_run: bool = True) -> dict[str, Any]:
        probe = self._simulation_adapter.normalize_observation(
            {
                "source_type": "simulation_cctv",
                "camera_id": "PREFLIGHT-CAM",
                "scenario_id": "preflight",
                "timestamp": _now_iso(),
                "event_type": "suspicious_person",
                "detected_class": "person",
                "confidence": 0.5,
                "metadata": {"simulated": True, "dry_run": True},
            }
        )
        return {
            "status": "healthy",
            "storage_dir": _relative_storage_uri(self._storage_dir),
            "records_dir": _relative_storage_uri(self._records_dir),
            "adapter_available": probe.source_type == "simulation_cctv",
            "promotion_available": True,
            "dry_run": dry_run,
            "persisted_records": len(list(self._records_dir.glob("*.json"))),
        }

    def _should_promote(self, event: NormalizedIntelligenceEvent) -> bool:
        event_type = str(event.event_type or "").lower()
        if event_type not in THREAT_EVENT_TYPES:
            return SEVERITY_ORDER.get(event.severity, 0) >= SEVERITY_ORDER["medium"]
        return True

    def _build_evidence_artifacts(
        self,
        session: UploadedVideoSession,
        report: UploadedVideoReport | None,
        events: list[UploadedVideoEvent],
        *,
        dry_run: bool,
    ) -> list[IntelligenceEvidenceArtifact]:
        artifacts: list[IntelligenceEvidenceArtifact] = [
            IntelligenceEvidenceArtifact(
                evidence_ref=f"uploaded_video:{session.session_id}:source_video",
                artifact_type="source_video",
                title=f"Source video: {session.original_filename}",
                storage_uri=session.storage_uri,
                content_type=str((session.metadata or {}).get("content_type") or "video/mp4"),
                hash_sha256=session.hash_sha256,
                metadata={"session_id": session.session_id, "original_filename": session.original_filename},
            )
        ]
        report_uri = session.report_uri
        if report_uri is None and report is not None:
            report_uri = (report.chain_of_custody or {}).get("report_artifact")
        if report_uri:
            artifacts.append(
                IntelligenceEvidenceArtifact(
                    evidence_ref=f"uploaded_video:{session.session_id}:report",
                    artifact_type="system_report",
                    title="Uploaded-video intelligence report",
                    storage_uri=str(report_uri),
                    content_type="application/json",
                    metadata={"session_id": session.session_id, "report_id": report.report_id if report else None},
                )
            )
            report_path = _resolve_storage_uri(str(report_uri))
            if report_path is not None:
                artifacts.extend(
                    [
                        IntelligenceEvidenceArtifact(
                            evidence_ref=f"uploaded_video:{session.session_id}:timeline",
                            artifact_type="timeline",
                            title="Uploaded-video event timeline",
                            storage_uri=_relative_storage_uri(report_path.with_name("timeline.json")),
                            content_type="application/json",
                            metadata={"session_id": session.session_id},
                        ),
                        IntelligenceEvidenceArtifact(
                            evidence_ref=f"uploaded_video:{session.session_id}:events",
                            artifact_type="events",
                            title="Uploaded-video raw events",
                            storage_uri=_relative_storage_uri(report_path.with_name("events.json")),
                            content_type="application/json",
                            metadata={"session_id": session.session_id},
                        ),
                    ]
                )
        for event in events:
            if event.snapshot_uri:
                artifacts.append(
                    IntelligenceEvidenceArtifact(
                        evidence_ref=f"uploaded_video:{session.session_id}:snapshot:{event.event_id}",
                        artifact_type="snapshot",
                        title=f"Snapshot for {event.event_type}",
                        storage_uri=event.snapshot_uri,
                        event_id=event.event_id,
                        content_type="image/jpeg",
                        metadata={"frame_index": event.frame_index, "time_offset_seconds": event.time_offset_seconds},
                    )
                )
            if event.replay_clip:
                artifacts.append(
                    IntelligenceEvidenceArtifact(
                        evidence_ref=f"uploaded_video:{session.session_id}:clip:{event.event_id}",
                        artifact_type="replay_clip",
                        title=f"Replay clip for {event.event_type}",
                        storage_uri=event.replay_clip.storage_uri,
                        event_id=event.event_id,
                        content_type=event.replay_clip.content_type,
                        hash_sha256=event.replay_clip.hash_sha256,
                        metadata={
                            "clip_id": event.replay_clip.clip_id,
                            "duration_seconds": event.replay_clip.duration_seconds,
                        },
                    )
                )
        if not dry_run:
            report_path = _resolve_storage_uri(report_uri) if report_uri else None
            if report_path is not None:
                artifacts.append(
                    IntelligenceEvidenceArtifact(
                        evidence_ref=f"uploaded_video:{session.session_id}:evidence_manifest",
                        artifact_type="evidence_manifest",
                        title="Uploaded-video command-center evidence manifest",
                        storage_uri=_relative_storage_uri(report_path.with_name("evidence_manifest.json")),
                        content_type="application/json",
                        metadata={"session_id": session.session_id},
                    )
                )
        return artifacts

    def _event_evidence_refs(self, event: UploadedVideoEvent, common_refs: list[str]) -> list[str]:
        refs = [
            ref
            for ref in common_refs
            if ref.endswith(":source_video") or ref.endswith(":report") or ref.endswith(":timeline") or ref.endswith(":events")
        ]
        refs.extend(ref for ref in common_refs if ref.endswith(f":{event.event_id}") or f":{event.event_id}:" in ref)
        return list(dict.fromkeys(refs))

    def _incident_from_event(
        self,
        session: UploadedVideoSession,
        event: NormalizedIntelligenceEvent,
        report: UploadedVideoReport | None,
    ) -> dict[str, Any]:
        created_at = _epoch_from_iso(event.timestamp)
        incident_id = f"inc-uv-{_slug(session.session_id)}-{_slug(event.event_id)}"
        track_ids = [event.track_id] if event.track_id else []
        risk = _risk_score(event.confidence, event.severity, float(event.metadata.get("risk_score") or 0.0))
        metadata = self._metadata_for_command_center(session, event, report, incident_id=incident_id)
        return {
            "incident_id": incident_id,
            "id": incident_id,
            "incident_type": event.event_type,
            "state": "OPEN",
            "severity": event.severity.upper(),
            "confidence": float(event.confidence or 0.0),
            "risk_score": risk,
            "camera_ids": [event.camera_id] if event.camera_id else [],
            "track_ids": track_ids,
            "identity_ids": [],
            "events": [event.model_dump(mode="json")],
            "anomalies": [],
            "timeline_refs": [
                {
                    "session_id": session.session_id,
                    "event_id": event.event_id,
                    "frame_index": event.frame_index,
                    "time_offset_seconds": event.metadata.get("time_offset_seconds"),
                }
            ],
            "created_at": created_at,
            "updated_at": created_at,
            "summary": event.description,
            "metadata": metadata,
        }

    def _alert_from_event(
        self,
        session: UploadedVideoSession,
        event: NormalizedIntelligenceEvent,
        incident: dict[str, Any],
        report: UploadedVideoReport | None,
    ) -> dict[str, Any]:
        created_at = _epoch_from_iso(event.timestamp)
        alert_id = f"alert-uv-{_slug(session.session_id)}-{_slug(event.event_id)}"
        risk = _risk_score(event.confidence, event.severity, float(event.metadata.get("risk_score") or 0.0))
        metadata = self._metadata_for_command_center(session, event, report, alert_id=alert_id, incident_id=incident["incident_id"])
        return {
            "alert_id": alert_id,
            "incident_id": incident["incident_id"],
            "event_ids": [event.event_id],
            "camera_ids": [event.camera_id] if event.camera_id else [],
            "track_ids": [event.track_id] if event.track_id else [],
            "identity_ids": [],
            "severity": event.severity,
            "state": "new",
            "title": f"{event.severity.upper()} uploaded-video {event.event_type.replace('_', ' ')}",
            "description": self._alert_description(session, event),
            "risk_score": risk,
            "confidence": float(event.confidence or 0.0),
            "created_at": created_at,
            "updated_at": created_at,
            "dispatched_at": None,
            "acknowledged_at": None,
            "resolved_at": None,
            "escalation_count": 0,
            "metadata": metadata,
        }

    def _alert_description(self, session: UploadedVideoSession, event: NormalizedIntelligenceEvent) -> str:
        offset = event.metadata.get("time_offset_seconds")
        when = f" at {float(offset):.2f}s" if isinstance(offset, (int, float)) else ""
        detected = f"{event.detected_class} " if event.detected_class else ""
        confidence = f" confidence={float(event.confidence):.2f}" if event.confidence is not None else ""
        return (
            f"Uploaded video '{session.original_filename}' produced a {detected}{event.event_type.replace('_', ' ')}"
            f" event{when}.{confidence}. Operator review required."
        )

    def _metadata_for_command_center(
        self,
        session: UploadedVideoSession,
        event: NormalizedIntelligenceEvent,
        report: UploadedVideoReport | None,
        **ids: str,
    ) -> dict[str, Any]:
        return {
            **ids,
            "source": "uploaded_video_promotion",
            "source_type": "uploaded_video",
            "alert_type": event.event_type,
            "uploaded_video": {
                "session_id": session.session_id,
                "original_filename": session.original_filename,
                "report_id": report.report_id if report else None,
                "report_uri": session.report_uri,
                "frame_index": event.frame_index,
                "time_offset_seconds": event.metadata.get("time_offset_seconds"),
            },
            "session_id": session.session_id,
            "report_id": report.report_id if report else None,
            "uploaded_video_event_id": event.event_id,
            "normalized_event_id": event.event_id,
            "detected_class": event.detected_class,
            "confidence": event.confidence,
            "frame_index": event.frame_index,
            "time_offset_seconds": event.metadata.get("time_offset_seconds"),
            "evidence_refs": list(event.evidence_refs),
        }

    def _persist_incident_event(self, event: NormalizedIntelligenceEvent, incident: dict[str, Any]) -> None:
        try:
            existing = self._incident_repository.get_event(event.event_id)
            metadata_patch = {
                "command_center": {
                    "incident_id": incident["incident_id"],
                    "alert_id": incident.get("metadata", {}).get("alert_id"),
                    "evidence_refs": list(event.evidence_refs),
                    "normalized_event": event.model_dump(mode="json"),
                }
            }
            if existing is not None:
                self._incident_repository.merge_event_metadata(event.event_id, metadata_patch)
                return
            self._incident_repository.append_event(
                IncidentEventRecord(
                    incident_id=incident["incident_id"],
                    event_id=event.event_id,
                    source_type=event.source_type,
                    camera_id=event.camera_id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    severity=event.severity,
                    risk_score=incident["risk_score"],
                    timestamp=event.timestamp,
                    frame_index=event.frame_index,
                    time_offset_seconds=event.metadata.get("time_offset_seconds"),
                    track_ids=[event.track_id] if event.track_id else [],
                    object_refs=[event.track_id] if event.track_id else [],
                    summary=event.description,
                    metadata={**event.metadata, **metadata_patch},
                )
            )
        except Exception:
            return

    def _persist_session_artifacts(self, session: UploadedVideoSession, record: UploadedVideoPromotionRecord) -> None:
        report_uri = session.report_uri or record.metadata.get("report_uri")
        report_path = _resolve_storage_uri(str(report_uri)) if report_uri else None
        if report_path is None:
            return
        normalized_path = report_path.with_name("normalized_intelligence_events.json")
        manifest_path = report_path.with_name("evidence_manifest.json")
        link_path = report_path.with_name("command_center_links.json")
        self._write_json(normalized_path, [event.model_dump(mode="json") for event in record.normalized_events])
        manifest = {
            "session_id": session.session_id,
            "generated_at": _now_iso(),
            "source_type": "uploaded_video",
            "artifacts": [item.model_dump(mode="json") for item in record.evidence_artifacts],
        }
        self._write_json(manifest_path, manifest)
        self._write_json(link_path, record.command_center_summary())

    def _analytics_payload(
        self,
        events: list[NormalizedIntelligenceEvent],
        alerts: list[dict[str, Any]],
        evidence_artifacts: list[IntelligenceEvidenceArtifact],
    ) -> dict[str, Any]:
        by_class: dict[str, int] = {}
        confidences: list[float] = []
        for event in events:
            key = event.detected_class or event.event_type
            by_class[key] = by_class.get(key, 0) + 1
            if event.confidence is not None:
                confidences.append(float(event.confidence))
        return {
            "detections_total": len(events),
            "detections_by_class": by_class,
            "alerts_generated": len(alerts),
            "high_severity_detections": sum(1 for event in events if SEVERITY_ORDER.get(event.severity, 0) >= SEVERITY_ORDER["high"]),
            "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "evidence_artifacts_created": len(evidence_artifacts),
        }

    def _record_path(self, session_id: str) -> Path:
        return self._records_dir / f"{_slug(session_id)}.json"

    def _iter_records(self) -> list[UploadedVideoPromotionRecord]:
        records: list[UploadedVideoPromotionRecord] = []
        for path in sorted(self._records_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            payload = self._read_json(path, None)
            if not payload:
                continue
            try:
                records.append(UploadedVideoPromotionRecord.model_validate(payload))
            except Exception:
                continue
        return records

    def _write_record(self, record: UploadedVideoPromotionRecord) -> None:
        self._write_json(self._record_path(record.session_id), record.model_dump(mode="json"))

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            temp_path.replace(path)


_COMMAND_CENTER_INTELLIGENCE_SERVICE: CommandCenterIntelligenceService | None = None
_COMMAND_CENTER_INTELLIGENCE_LOCK = threading.Lock()


def get_command_center_intelligence_service() -> CommandCenterIntelligenceService:
    global _COMMAND_CENTER_INTELLIGENCE_SERVICE
    with _COMMAND_CENTER_INTELLIGENCE_LOCK:
        if _COMMAND_CENTER_INTELLIGENCE_SERVICE is None:
            _COMMAND_CENTER_INTELLIGENCE_SERVICE = CommandCenterIntelligenceService()
        return _COMMAND_CENTER_INTELLIGENCE_SERVICE
