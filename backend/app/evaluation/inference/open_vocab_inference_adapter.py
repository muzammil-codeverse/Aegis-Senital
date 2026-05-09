"""Phase 26 — Open-vocab inference adapter for offline benchmark evaluation."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from backend.app.evaluation.inference.base import (
    DetectionBox,
    DetectionModelAdapter,
    DetectionPrediction,
)

logger = logging.getLogger(__name__)


class OpenVocabInferenceAdapter(DetectionModelAdapter):
    """
    Wraps the existing GroundingDINO adapter for offline evaluation.

    Does not mutate production state (no result-store writes, no event publishing).
    Safe to instantiate during benchmarking without affecting the running runtime.
    """

    def __init__(
        self,
        name: str = "grounding_dino",
        device: str = "cpu",
        prompt_text: str = "weapon",
        threshold: float = 0.35,
        config: dict | None = None,
    ) -> None:
        self._name = name
        self._device = device
        self._prompt_text = prompt_text
        self._threshold = threshold
        self._config = config or {}
        self._adapter = None

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str | None:
        return None

    @property
    def device(self) -> str:
        return self._device

    def load(self) -> None:
        try:
            from inference.open_vocab.grounding_dino_adapter import GroundingDINOAdapter
            self._adapter = GroundingDINOAdapter(config=self._config)
        except ImportError as exc:
            logger.warning("GroundingDINOAdapter import failed: %s — open-vocab eval degraded", exc)
            self._adapter = None

    def is_loaded(self) -> bool:
        return self._adapter is not None and self._adapter.is_available()

    def predict(self, image_path: str, confidence_threshold: float = 0.35) -> DetectionPrediction:
        stem = Path(image_path).stem
        if not self.is_loaded():
            return DetectionPrediction(
                sample_id=stem,
                model_name=self._name,
                device=self._device,
                error="Open-vocab adapter unavailable — model not loaded",
            )

        t0 = time.perf_counter()
        try:
            raw = self._adapter.detect(
                image_path,
                [self._prompt_text],
                {"box_threshold": confidence_threshold, "text_threshold": 0.25},
            )
        except Exception as exc:
            return DetectionPrediction(
                sample_id=stem,
                model_name=self._name,
                device=self._device,
                latency_ms=round((time.perf_counter() - t0) * 1000, 3),
                error=str(exc),
            )

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)
        detections = [
            DetectionBox(
                bbox=d.get("bbox", []),
                score=d.get("confidence", 0.0),
                class_id=0,
                label=d.get("label", self._prompt_text),
            )
            for d in raw
            if d.get("confidence", 0.0) >= confidence_threshold
        ]

        return DetectionPrediction(
            sample_id=stem,
            detections=detections,
            latency_ms=latency_ms,
            model_name=self._name,
            device=self._device,
        )

    def unload(self) -> None:
        self._adapter = None
