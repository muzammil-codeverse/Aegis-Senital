from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DetectedObject:
    type: str
    confidence: float
    bbox: list           # [x1, y1, x2, y2]
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
