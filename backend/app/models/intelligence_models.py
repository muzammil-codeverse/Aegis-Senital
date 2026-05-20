from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


IntelligenceSourceType = Literal[
    "uploaded_video",
    "simulation_cctv",
    "drone_camera",
    "live_stream",
    "scenario_observation",
]

IntelligenceSeverity = Literal["info", "low", "medium", "high", "critical"]

IntelligenceEventType = Literal[
    "weapon_detected",
    "phone_detected",
    "suspicious_person",
    "person_tracking",
    "zone_intrusion",
    "suspect_movement",
    "drone_observation",
    "camera_handoff",
    "scenario_incident",
]

PromotionStatus = Literal["dry_run", "no_detections", "promoted", "failed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sensitive = {
        "embedding",
        "embeddings",
        "face_embedding",
        "appearance_embedding",
        "raw_frame",
        "raw_image",
        "frame_bytes",
    }
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if lowered in sensitive or "embedding" in lowered:
            continue
        cleaned[str(key)] = _json_safe(item)
    return cleaned


class IntelligenceBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("source_type", "event_type", "severity", mode="before", check_fields=False)
    @classmethod
    def _lower_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("evidence_refs", "alert_ids", "incident_ids", "case_ids", mode="before", check_fields=False)
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            output.append(text)
        return output

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _metadata_validator(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)


class NormalizedIntelligenceEvent(IntelligenceBaseModel):
    event_id: str = Field(default_factory=lambda: _gen_id("nie"))
    source_type: IntelligenceSourceType
    source_id: str
    session_id: str | None = None
    stream_id: str | None = None
    camera_id: str | None = None
    drone_id: str | None = None
    frame_index: int | None = None
    timestamp: str = Field(default_factory=_now_iso)
    zone: str | None = None
    location: dict[str, Any] | None = None
    detected_class: str | None = None
    confidence: float | None = None
    bounding_box: dict[str, Any] | list[float] | None = None
    track_id: str | None = None
    event_type: str
    severity: IntelligenceSeverity = "medium"
    description: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntelligenceEvidenceArtifact(IntelligenceBaseModel):
    evidence_ref: str
    artifact_type: str
    title: str
    storage_uri: str | None = None
    event_id: str | None = None
    content_type: str | None = None
    hash_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoPromotionRecord(IntelligenceBaseModel):
    promotion_id: str = Field(default_factory=lambda: _gen_id("uvpromo"))
    session_id: str
    report_id: str | None = None
    status: PromotionStatus = "promoted"
    source_type: Literal["uploaded_video"] = "uploaded_video"
    promoted_at: str = Field(default_factory=_now_iso)
    normalized_events: list[NormalizedIntelligenceEvent] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    incident_ids: list[str] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_artifacts: list[IntelligenceEvidenceArtifact] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    incidents: list[dict[str, Any]] = Field(default_factory=list)
    alert_history: list[dict[str, Any]] = Field(default_factory=list)
    analytics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def command_center_summary(self) -> dict[str, Any]:
        return {
            "promotion_id": self.promotion_id,
            "status": self.status,
            "source_type": self.source_type,
            "session_id": self.session_id,
            "report_id": self.report_id,
            "alert_ids": list(self.alert_ids),
            "incident_ids": list(self.incident_ids),
            "case_ids": list(self.case_ids),
            "evidence_refs": list(self.evidence_refs),
            "evidence_artifacts": [item.model_dump(mode="json") for item in self.evidence_artifacts],
            "normalized_event_count": len(self.normalized_events),
            "promoted_at": self.promoted_at,
            "analytics": dict(self.analytics),
        }
