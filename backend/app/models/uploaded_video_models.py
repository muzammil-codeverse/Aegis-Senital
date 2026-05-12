from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UploadedVideoStatus = Literal["uploaded", "queued", "processing", "completed", "failed", "cancelled"]
UploadedVideoSourceType = Literal["uploaded_video"]


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
    return {str(key): _json_safe(item) for key, item in value.items()}


class UploadedVideoBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("metadata", mode="before", check_fields=False)
    @classmethod
    def _metadata_validator(cls, value: Any) -> dict[str, Any]:
        return _coerce_metadata(value)

    @field_validator("source_type", "status", mode="before", check_fields=False)
    @classmethod
    def _lower_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("event_ids", "camera_ids", "track_ids", mode="before", check_fields=False)
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        values: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
        return values


class UploadedVideoProgress(UploadedVideoBaseModel):
    frames_processed: int = 0
    total_frames: int = 0
    percent: float = 0.0


class UploadedVideoProcessingOptions(UploadedVideoBaseModel):
    target_fps: int | None = None
    max_frames: int | None = None
    frame_stride: int | None = None
    generate_event_timeline: bool | None = None
    generate_snapshots: bool | None = None
    generate_replay_clips: bool | None = None
    attach_source_video_as_evidence: bool | None = None
    attach_snapshots_as_evidence: bool | None = None
    auto_create_case: bool = False
    linked_case_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoSession(UploadedVideoBaseModel):
    session_id: str = Field(default_factory=lambda: _gen_id("uvs"))
    source_type: UploadedVideoSourceType = "uploaded_video"
    original_filename: str
    safe_filename: str
    storage_uri: str
    hash_sha256: str
    duration_seconds: float = 0.0
    frame_count: int = 0
    fps: float = 0.0
    status: UploadedVideoStatus = "uploaded"
    progress: UploadedVideoProgress = Field(default_factory=UploadedVideoProgress)
    created_by: str
    created_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    linked_case_id: str | None = None
    report_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoUploadRequest(UploadedVideoBaseModel):
    options: UploadedVideoProcessingOptions = Field(default_factory=UploadedVideoProcessingOptions)


class UploadedVideoUploadResponse(UploadedVideoBaseModel):
    session: UploadedVideoSession
    status: str = "uploaded"
    detail: str | None = None


class UploadedVideoProcessingStatus(UploadedVideoBaseModel):
    session_id: str
    status: UploadedVideoStatus
    progress: UploadedVideoProgress = Field(default_factory=UploadedVideoProgress)
    last_error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    active: bool = False
    report_ready: bool = False
    event_count: int = 0


class UploadedVideoFrameResult(UploadedVideoBaseModel):
    frame_index: int
    timestamp: str
    time_offset_seconds: float = 0.0
    detection_count: int = 0
    event_ids: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoReplayClipMetadata(UploadedVideoBaseModel):
    """SHA-256-backed replay clip artifact for a single uploaded-video event."""

    clip_id: str
    session_id: str
    event_id: str
    start_time_seconds: float
    end_time_seconds: float
    duration_seconds: float
    storage_uri: str
    hash_sha256: str
    size_bytes: int = 0
    content_type: str = "video/mp4"
    integrity_status: str = "verified"
    created_at: str = Field(default_factory=_now_iso)


class UploadedVideoEvent(UploadedVideoBaseModel):
    event_id: str = Field(default_factory=lambda: _gen_id("uve"))
    session_id: str
    source_type: UploadedVideoSourceType = "uploaded_video"
    event_type: str
    severity: str = "medium"
    risk_score: float = 0.0
    timestamp: str = Field(default_factory=_now_iso)
    frame_index: int | None = None
    time_offset_seconds: float | None = None
    camera_ids: list[str] = Field(default_factory=list)
    track_ids: list[str] = Field(default_factory=list)
    snapshot_uri: str | None = None
    replay_clip: UploadedVideoReplayClipMetadata | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoTimelineItem(UploadedVideoBaseModel):
    timeline_id: str = Field(default_factory=lambda: _gen_id("uvtl"))
    session_id: str
    event_id: str | None = None
    timestamp: str = Field(default_factory=_now_iso)
    time_offset_seconds: float = 0.0
    frame_index: int | None = None
    title: str
    description: str = ""
    severity: str = "medium"
    snapshot_uri: str | None = None
    replay_clip: UploadedVideoReplayClipMetadata | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoReport(UploadedVideoBaseModel):
    report_id: str = Field(default_factory=lambda: _gen_id("uvr"))
    session_id: str
    generated_at: str = Field(default_factory=_now_iso)
    generated_by: str = "system"
    video_metadata: dict[str, Any] = Field(default_factory=dict)
    integrity: dict[str, Any] = Field(default_factory=dict)
    processing_options: dict[str, Any] = Field(default_factory=dict)
    models_used: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[UploadedVideoTimelineItem] = Field(default_factory=list)
    detections_summary: dict[str, Any] = Field(default_factory=dict)
    anomaly_summary: dict[str, Any] = Field(default_factory=dict)
    identity_summary: dict[str, Any] = Field(default_factory=dict)
    segmentation_summary: dict[str, Any] = Field(default_factory=dict)
    chain_of_custody: dict[str, Any] = Field(default_factory=dict)
    replay_clips: list[dict[str, Any]] = Field(default_factory=list)
    replay_summary: dict[str, Any] = Field(default_factory=dict)
    model_caveats: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedVideoCaseCreationRequest(UploadedVideoBaseModel):
    title: str | None = None
    description: str | None = None
    attach_source_video: bool = True
    attach_snapshots: bool = True
    attach_report: bool = True
    attach_replay_clips: bool = True
    priority: str = "high"
    severity: str = "high"
    metadata: dict[str, Any] = Field(default_factory=dict)
