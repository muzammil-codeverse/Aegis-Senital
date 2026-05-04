from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return str(uuid.uuid4())


# ─── Core detection types ──────────────────────────────────────────────────────

@dataclass
class Detection:
    """Single object detection from one inference model."""
    class_name: str       # normalized: "weapon" | "phone" | "person" | raw label
    bbox: list            # [x1, y1, x2, y2]
    confidence: float
    source_model: str     # "weapon_model" | "phone_model"
    detection_id: str = field(default_factory=_gen_id)
    camera_id: str = "default"
    face_embedding: list = field(default_factory=list)
    appearance_embedding: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "detection_id": self.detection_id,
            "class": self.class_name,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "source_model": self.source_model,
            "camera_id": self.camera_id,
            "face_embedding": self.face_embedding,
            "appearance_embedding": self.appearance_embedding,
            "metadata": self.metadata,
        }


@dataclass
class Track:
    """
    Persistent identity assigned to a detection across frames.

    Phase-7 additions (velocity, stability_score, confidence_trend) default
    to safe zero-values so all existing code that constructs Track objects
    without them continues to work unchanged.
    """
    track_id: int
    class_name: str
    bbox: list            # [x1, y1, x2, y2] — most recent confirmed position
    confidence: float
    last_seen_frame: int
    missed_frames: int = 0
    # Phase 7 — motion + stability telemetry (optional, backwards-safe)
    velocity: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])  # [dx,dy,dw,dh]
    stability_score: float = 0.0    # 0.0 = brand new, 1.0 = highly stable
    confidence_trend: float = 0.0   # positive = growing, negative = declining
    # Phase 8 — DB-backed cross-session identity (None until persisted)
    persistent_track_id: str | None = None
    track_uuid: str = field(default_factory=_gen_id)
    identity_id: str | None = None
    camera_id: str = "default"
    first_seen_at: str = field(default_factory=_now_iso)
    last_seen_at: str = field(default_factory=_now_iso)
    status: str = "ACTIVE"
    face_embedding: list = field(default_factory=list)
    appearance_embedding: list = field(default_factory=list)
    identity_confidence: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.persistent_track_id is None and self.identity_id is not None:
            self.persistent_track_id = self.identity_id

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "last_seen_frame": self.last_seen_frame,
            "missed_frames": self.missed_frames,
            "velocity": self.velocity,
            "stability_score": self.stability_score,
            "confidence_trend": self.confidence_trend,
            "persistent_track_id": self.persistent_track_id or self.identity_id,
            "track_uuid": self.track_uuid,
            "identity_id": self.identity_id,
            "camera_id": self.camera_id,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "status": self.status,
            "face_embedding": self.face_embedding,
            "appearance_embedding": self.appearance_embedding,
            "identity_confidence": self.identity_confidence,
            "metadata": self.metadata,
        }


@dataclass
class TrackTimeSeries:
    """
    Per-track temporal data store maintained by EventBuffer.

    Accumulates confirmed (non-predicted) observations per track so that
    downstream engines can query multi-frame statistics rather than relying
    on single-frame values.
    """
    track_id: int
    class_name: str
    bbox_series: list = field(default_factory=list)           # list[list[float]]
    confidence_series: list = field(default_factory=list)     # list[float]
    threat_score_series: list = field(default_factory=list)   # list[float]
    frame_ids: list = field(default_factory=list)             # list[int]
    timestamps: list = field(default_factory=list)            # list[str ISO-8601]
    identity_id: str | None = None
    camera_ids: list = field(default_factory=list)
    identity_confidence_series: list = field(default_factory=list)

    def append(
        self,
        bbox: list,
        confidence: float,
        frame_id: int,
        threat_score: float = 0.0,
        camera_id: str = "default",
        identity_id: str | None = None,
        identity_confidence: float = 0.0,
    ) -> None:
        self.bbox_series.append(list(bbox))
        self.confidence_series.append(confidence)
        self.threat_score_series.append(threat_score)
        self.frame_ids.append(frame_id)
        self.timestamps.append(_now_iso())
        self.camera_ids.append(camera_id)
        self.identity_confidence_series.append(identity_confidence)
        if identity_id is not None:
            self.identity_id = identity_id

    def rolling_mean_confidence(self, window: int = 10) -> float:
        recent = self.confidence_series[-window:]
        return round(sum(recent) / len(recent), 3) if recent else 0.0

    def confidence_trend(self, window: int = 5) -> float:
        """Positive = growing, negative = declining."""
        recent = self.confidence_series[-window:]
        if len(recent) < 2:
            return 0.0
        return round((recent[-1] - recent[0]) / len(recent), 4)

    def mean_threat_score(self, window: int = 10) -> float:
        recent = self.threat_score_series[-window:]
        return round(sum(recent) / len(recent), 3) if recent else 0.0

    @property
    def duration_frames(self) -> int:
        """Number of frames in which this track was actually detected."""
        return len(self.frame_ids)

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "duration_frames": self.duration_frames,
            "mean_confidence": self.rolling_mean_confidence(),
            "mean_threat_score": self.mean_threat_score(),
            "confidence_trend": self.confidence_trend(),
            "identity_id": self.identity_id,
            "camera_ids": list(dict.fromkeys(self.camera_ids)),
        }


@dataclass
class Event:
    """
    Threat event produced by the EventEngine.

    severity_score is the continuous 0–1 threat value; severity is the
    discretised label derived from it.  confidence_score is kept for
    backwards compatibility with the legacy pipeline.
    """
    event_type: str
    severity: str                    # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    track_ids: list = field(default_factory=list)
    frame_range: tuple = field(default_factory=lambda: (0, 0))
    confidence_score: float = 0.0    # legacy compat
    # Phase 8 fields
    event_id: str = field(default_factory=_gen_id)
    severity_score: float = 0.0      # continuous threat score ∈ [0, 1]
    contributing_tracks: list = field(default_factory=list)   # list[dict]
    time_window: tuple = field(default_factory=lambda: (0.0, 0.0))  # seconds
    confidence_distribution: dict = field(default_factory=dict)
    risk_score: float = 0.0
    timestamp: str = field(default_factory=_now_iso)
    track_ref_ids: list = field(default_factory=list)
    identity_ids: list = field(default_factory=list)
    camera_ids: list = field(default_factory=list)
    event_vector: list = field(default_factory=list)
    persisted: bool = False
    metadata: dict = field(default_factory=dict)
    # Phase 5 — intelligence layer
    priority_level: str = "LOW"     # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    def __post_init__(self) -> None:
        if self.risk_score == 0.0 and self.severity_score > 0.0:
            self.risk_score = self.severity_score

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "severity_score": self.severity_score,
            "priority_level": self.priority_level,
            "track_ids": list(self.track_ids),
            "frame_range": list(self.frame_range),
            "confidence_score": self.confidence_score,
            "contributing_tracks": self.contributing_tracks,
            "time_window": list(self.time_window),
            "confidence_distribution": self.confidence_distribution,
            "risk_score": self.risk_score,
            "timestamp": self.timestamp,
            "track_ref_ids": list(self.track_ref_ids),
            "identity_ids": list(self.identity_ids),
            "camera_ids": list(self.camera_ids),
            "event_vector": list(self.event_vector),
            "persisted": self.persisted,
            "metadata": self.metadata,
        }


@dataclass
class Scenario:
    """
    High-level behavioral scenario aggregated from an event cluster.

    scenario_id, temporal_span, and confidence_score are Phase-9 additions;
    all have safe defaults so legacy instantiation still works.
    """
    scenario_type: str
    events: list = field(default_factory=list)    # list[Event]
    risk_level: str = "LOW"
    summary: str = ""
    # Phase 9 fields
    scenario_id: str = field(default_factory=_gen_id)
    temporal_span: tuple = field(default_factory=lambda: (0, 0))
    confidence_score: float = 0.0
    event_cluster: list = field(default_factory=list)
    # Lifecycle state: ACTIVE | ESCALATING | RESOLVED | FALSE_ALARM
    status: str = "ACTIVE"
    start_time: str = field(default_factory=_now_iso)
    end_time: str | None = None
    camera_ids: list = field(default_factory=list)
    identity_ids: list = field(default_factory=list)
    scenario_vector: list = field(default_factory=list)
    persisted: bool = False
    metadata: dict = field(default_factory=dict)
    # Phase 5 — intelligence layer
    escalation_level: str = "NONE"  # "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "events": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.events],
            "risk_level": self.risk_level,
            "summary": self.summary,
            "temporal_span": list(self.temporal_span),
            "confidence_score": self.confidence_score,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "camera_ids": list(self.camera_ids),
            "identity_ids": list(self.identity_ids),
            "scenario_vector": list(self.scenario_vector),
            "persisted": self.persisted,
            "escalation_level": self.escalation_level,
            "metadata": self.metadata,
        }


@dataclass
class FramePacket:
    """Complete per-frame data bundle passed through the inference pipeline."""
    frame_id: int
    timestamp: str = field(default_factory=_now_iso)
    detections: list = field(default_factory=list)   # list[Detection]
    tracks: list = field(default_factory=list)        # list[Track]
    camera_id: str = "default"
    frame_width: int = 0
    frame_height: int = 0
    metadata: dict = field(default_factory=dict)
    image: Any | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "detections": [d.to_dict() if hasattr(d, "to_dict") else d for d in self.detections],
            "tracks": [t.to_dict() if hasattr(t, "to_dict") else t for t in self.tracks],
            "camera_id": self.camera_id,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "metadata": self.metadata,
        }


# ─── Legacy types (backwards compatibility with backend/video_service.py) ─────

@dataclass
class DetectedObject:
    type: str
    confidence: float
    bbox: list
    tracking_id: int | None = None


@dataclass
class DetectionResult:
    frame_id: int
    objects: list = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "objects": [
                {
                    "type": obj.type,
                    "confidence": obj.confidence,
                    "bbox": obj.bbox,
                    "tracking_id": obj.tracking_id,
                }
                for obj in self.objects
            ],
        }
