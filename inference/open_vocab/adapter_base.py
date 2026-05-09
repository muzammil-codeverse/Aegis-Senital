from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class OpenVocabDetectorAdapter(ABC):
    """Abstract base for open-vocabulary detector adapters. Lazy-load only."""

    def load(self) -> None:
        """Load model weights. Called explicitly, never at import time."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if model is loaded and ready."""
        ...

    @abstractmethod
    def get_status(self) -> dict:
        """Return status dict with available, provider, model_id, reason."""
        ...

    @abstractmethod
    def detect(
        self,
        image: Any,
        prompts: list[str],
        thresholds: dict | None = None,
    ) -> list[dict]:
        """
        Run open-vocab detection.
        Returns list of dicts: {label, confidence, bbox, source_model}
        Never returns fake detections. Returns [] if unavailable.
        """
        ...

    def unload(self) -> None:
        """Release model resources."""
        ...
