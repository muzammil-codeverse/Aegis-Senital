from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StreamStatus = Literal["healthy", "degraded", "reconnecting", "failed", "stopped"]
StreamSourceType = Literal["rtsp", "file", "webcam", "drone_simulation"]
PreviewType = Literal["webrtc", "hls", "mjpeg"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StreamingBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class StreamSourceConfig(StreamingBaseModel):
    camera_id: str
    source_type: StreamSourceType
    source_uri: str | None = None
    enabled: bool = True
    loop_file: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RtspStreamConfig(StreamingBaseModel):
    source: StreamSourceConfig
    reconnect_enabled: bool = True
    reconnect_max_attempts: int = 10
    reconnect_initial_backoff_seconds: float = 1.0
    reconnect_max_backoff_seconds: float = 30.0
    reconnect_jitter: bool = True
    read_timeout_seconds: float = 10.0
    stale_frame_timeout_seconds: float = 5.0


class StreamHealth(StreamingBaseModel):
    camera_id: str
    status: StreamStatus = "stopped"
    source_type: StreamSourceType = "rtsp"
    last_frame_at: str | None = None
    fps_decode: float = 0.0
    fps_processed: float = 0.0
    frame_queue_depth: int = 0
    dropped_frames_total: int = 0
    reconnect_attempts: int = 0
    latency_ms: float = 0.0
    last_error: str | None = None


class StreamFrameStats(StreamingBaseModel):
    camera_id: str
    stream_id: str | None = None
    source_type: StreamSourceType = "rtsp"
    last_frame_at: str | None = None
    last_source_timestamp: str | None = None
    fps_decode: float = 0.0
    fps_processed: float = 0.0
    frame_queue_depth: int = 0
    dropped_frames_total: int = 0
    frames_decoded_total: int = 0
    frames_processed_total: int = 0
    reconnect_attempts: int = 0
    latency_ms: float = 0.0
    preview_clients_active: int = 0
    updated_at: str = Field(default_factory=_now_iso)


class StreamPreviewSession(StreamingBaseModel):
    camera_id: str
    preview_type: PreviewType
    session_id: str
    status: str = "idle"
    client_count: int = 0
    started_at: str | None = None
    last_seen_at: str | None = None
    detail: str | None = None


class WebRTCOfferRequest(StreamingBaseModel):
    sdp: str
    type: Literal["offer"] = "offer"


class WebRTCAnswerResponse(StreamingBaseModel):
    sdp: str | None = None
    type: str = "answer"
    status: str = "ok"
    detail: str | None = None
    preview_url: str | None = None


class HlsPlaylistInfo(StreamingBaseModel):
    camera_id: str
    available: bool = False
    playlist_url: str | None = None
    output_dir: str | None = None
    segment_seconds: int = 2
    playlist_length: int = 6
    detail: str | None = None


class ReplayClipRequest(StreamingBaseModel):
    event_id: str | None = None
    case_id: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    seconds_before: int = 10
    seconds_after: int = 20
    include_hash: bool = False
    attach_to_case: bool = False
    severity: str | None = None


class ReplayClipResponse(StreamingBaseModel):
    clip_id: str
    camera_id: str
    status: str = "pending"
    created_at: str = Field(default_factory=_now_iso)
    file_path: str | None = None
    metadata_path: str | None = None
    download_url: str | None = None
    hash_sha256: str | None = None
    attached_case_id: str | None = None
    detail: str | None = None


class StreamDiagnosticReport(StreamingBaseModel):
    camera_id: str
    stream_id: str | None = None
    status: StreamStatus = "stopped"
    health: StreamHealth
    stats: StreamFrameStats
    preview_sessions: list[StreamPreviewSession] = Field(default_factory=list)
    hls: HlsPlaylistInfo | None = None
    replay_enabled: bool = False
    dependencies: dict[str, Any] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
