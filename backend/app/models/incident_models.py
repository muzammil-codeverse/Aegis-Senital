from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


IncidentSourceType = Literal[
    "live_stream",
    "uploaded_video",
    "simulation_cctv",
    "drone_camera",
    "scenario_observation",
    "drone_simulation",
    "file_simulation",
]


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


def _sanitize_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    sensitive_keys = {
        "embedding",
        "embeddings",
        "face_embedding",
        "appearance_embedding",
        "raw_frame",
        "raw_image",
        "image_blob",
        "frame_bytes",
    }
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        lowered = str(key).lower()
        if lowered in sensitive_keys or "embedding" in lowered:
            continue
        cleaned[str(key)] = _json_safe(item)
    return cleaned


class IncidentBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _metadata_validator(cls, value: Any) -> dict[str, Any]:
        return _sanitize_metadata(value)

    @field_validator(
        "source_type",
        "severity",
        "event_type",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _lower_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "camera_ids",
        "track_ids",
        "object_refs",
        "identity_ids",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
        return unique


class IncidentEventRecord(IncidentBaseModel):
    incident_id: str = Field(default_factory=lambda: _gen_id("inc"))
    event_id: str
    source_type: IncidentSourceType
    camera_id: str | None = None
    session_id: str | None = None
    case_id: str | None = None
    event_type: str
    severity: str = "medium"
    risk_score: float = 0.0
    timestamp: str = Field(default_factory=_now_iso)
    frame_index: int | None = None
    time_offset_seconds: float | None = None
    track_ids: list[str] = Field(default_factory=list)
    object_refs: list[str] = Field(default_factory=list)
    identity_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)

    @property
    def source_id(self) -> str | None:
        return self.session_id or self.camera_id


class IncidentEventQuery(IncidentBaseModel):
    source_type: IncidentSourceType | None = None
    camera_id: str | None = None
    session_id: str | None = None
    case_id: str | None = None
    event_type: str | None = None
    severity: str | None = None
    limit: int = 100
