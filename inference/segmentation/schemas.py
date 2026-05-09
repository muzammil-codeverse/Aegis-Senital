from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SEGMENTATION_SUCCESS = "success"
SEGMENTATION_SKIPPED = "skipped"
SEGMENTATION_FAILED = "failed"
SEGMENTATION_PROVIDER_UNAVAILABLE = "provider_unavailable"

ALLOWED_SEGMENTATION_STATUSES = frozenset(
    {
        SEGMENTATION_SUCCESS,
        SEGMENTATION_SKIPPED,
        SEGMENTATION_FAILED,
        SEGMENTATION_PROVIDER_UNAVAILABLE,
    }
)


@dataclass
class SegmentationResult:
    detection_id: str
    label: str
    bbox: list[float]
    mask_encoding: str
    mask: dict | list | None
    mask_area: int
    bbox_area: int
    mask_confidence: float | None
    refinement_status: str
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.refinement_status not in ALLOWED_SEGMENTATION_STATUSES:
            raise ValueError(f"invalid segmentation status: {self.refinement_status}")
        self.bbox = [float(v) for v in self.bbox[:4]]
        self.mask_area = int(max(0, self.mask_area))
        self.bbox_area = int(max(0, self.bbox_area))
        if self.mask_confidence is not None:
            self.mask_confidence = float(self.mask_confidence)

    def to_dict(self, *, include_mask: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_mask:
            payload.pop("mask", None)
        return payload

    def to_event_metadata(self) -> dict[str, Any]:
        return {
            "detection_id": self.detection_id,
            "label": self.label,
            "bbox": list(self.bbox),
            "mask_encoding": self.mask_encoding,
            "mask_area": self.mask_area,
            "bbox_area": self.bbox_area,
            "mask_confidence": self.mask_confidence,
            "refinement_status": self.refinement_status,
            "failure_reason": self.failure_reason,
        }


@dataclass
class SegmentationHealth:
    enabled: bool
    provider: str
    loaded: bool
    device: str
    status: str
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
