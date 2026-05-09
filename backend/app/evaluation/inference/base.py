"""Phase 26 — Common detection inference interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectionBox:
    bbox: list[float]  # [x1, y1, x2, y2] absolute pixels
    score: float
    class_id: int
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "bbox": self.bbox,
            "score": round(self.score, 4),
            "class_id": self.class_id,
            "label": self.label,
        }


@dataclass
class DetectionPrediction:
    sample_id: str
    detections: list[DetectionBox] = field(default_factory=list)
    latency_ms: float = 0.0
    model_name: str = ""
    model_version: str | None = None
    device: str = "cpu"
    image_width: int = 0
    image_height: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "sample_id": self.sample_id,
            "detections": [d.to_dict() for d in self.detections],
            "latency_ms": round(self.latency_ms, 3),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "device": self.device,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "error": self.error,
        }


class DetectionModelAdapter(ABC):
    """Common interface for all detection model adapters used in benchmark evaluation."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def model_version(self) -> str | None: ...

    @property
    @abstractmethod
    def device(self) -> str: ...

    @abstractmethod
    def load(self) -> None:
        """Load model weights. Raises FileNotFoundError if path is missing."""

    @abstractmethod
    def is_loaded(self) -> bool:
        """Return True if the model is ready for inference."""

    @abstractmethod
    def predict(self, image_path: str, confidence_threshold: float = 0.25) -> DetectionPrediction:
        """Run inference on one image. Returns normalized DetectionPrediction."""

    def warmup(self, image_size: int = 640, n: int = 3) -> None:
        """Optional: run n dummy inferences to stabilize latency measurements."""

    def unload(self) -> None:
        """Release GPU memory and model weights."""
