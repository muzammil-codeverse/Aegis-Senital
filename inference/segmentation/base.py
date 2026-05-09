from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from inference.segmentation.schemas import SegmentationResult


class SegmentationAdapter(ABC):
    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def unload(self) -> None:
        ...

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def segment_boxes(
        self,
        image: Any,
        boxes: list[list[float]],
        labels: list[str] | None = None,
    ) -> list[SegmentationResult]:
        ...

    def health(self) -> dict[str, Any]:
        return {
            "loaded": self.is_loaded(),
            "status": "healthy" if self.is_loaded() else "degraded",
        }
