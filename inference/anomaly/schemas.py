from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return str(uuid.uuid4())


ANOMALY_TYPES = frozenset({
    "violence",
    "loitering",
    "abandoned_object",
    "panic_running",
    "restricted_zone",
    "crowd_anomaly",
    "generic",
})

SEVERITY_LABELS = ("low", "medium", "high", "critical")

# Review-safe display labels — never claim "crime confirmed"
DISPLAY_LABELS: dict[str, str] = {
    "violence": "possible violence",
    "loitering": "possible loitering",
    "abandoned_object": "possible abandoned object",
    "panic_running": "possible panic/running",
    "restricted_zone": "possible restricted-zone anomaly",
    "crowd_anomaly": "possible crowd anomaly",
    "generic": "possible video anomaly",
}


@dataclass
class AnomalyWindow:
    """Rolling temporal window for one camera, passed to detection engines."""
    camera_id: str
    window_id: str = field(default_factory=_gen_id)
    start_ts: str = field(default_factory=_now_iso)
    end_ts: str = field(default_factory=_now_iso)
    frames: list = field(default_factory=list)        # list[dict] — lightweight frame refs
    detections: list = field(default_factory=list)    # list[dict]
    tracks: list = field(default_factory=list)        # list[dict]
    segmentation: dict | None = None

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "window_id": self.window_id,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "frame_count": len(self.frames),
            "detection_count": len(self.detections),
            "track_count": len(self.tracks),
        }


@dataclass
class AnomalyPrediction:
    """Output of the anomaly subsystem for one detected anomaly event."""
    camera_id: str
    anomaly_type: str
    score: float
    severity: str
    confidence: float
    source: str
    duration_seconds: float
    track_ids: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    requires_review: bool = True
    window_id: str = field(default_factory=_gen_id)
    timestamp: str = field(default_factory=_now_iso)

    def display_label(self) -> str:
        return DISPLAY_LABELS.get(self.anomaly_type, "possible video anomaly")

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "window_id": self.window_id,
            "anomaly_type": self.anomaly_type,
            "display_label": self.display_label(),
            "score": round(self.score, 4),
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "duration_seconds": round(self.duration_seconds, 2),
            "track_ids": list(self.track_ids),
            "evidence": self.evidence,
            "requires_review": self.requires_review,
            "timestamp": self.timestamp,
        }
