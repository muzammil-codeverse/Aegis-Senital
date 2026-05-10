from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

from inference.anomaly.schemas import AnomalyPrediction, AnomalyWindow

logger = logging.getLogger(__name__)

PROVIDERS = ("rule_only", "pretrained_video", "violence_visual", "custom_clip_model")


class AnomalyModelAdapter(ABC):
    """Abstract base for all anomaly model adapters."""

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def predict_clip(
        self, frames: list, metadata: dict | None = None
    ) -> AnomalyPrediction | None: ...

    def health(self) -> dict:
        return {"loaded": self.is_loaded(), "provider": self.__class__.__name__}


class RuleOnlyAdapter(AnomalyModelAdapter):
    """Stub adapter that reports rule_only — no model weights needed."""

    def load(self) -> None:
        pass

    def is_loaded(self) -> bool:
        return True

    def predict_clip(
        self, frames: list, metadata: dict | None = None
    ) -> AnomalyPrediction | None:
        return None  # rule_only; predictions come from RuleEngine

    def health(self) -> dict:
        return {"loaded": True, "provider": "rule_only", "status": "healthy"}


class PretrainedVideoAdapter(AnomalyModelAdapter):
    """
    Placeholder for a pretrained video anomaly model (e.g. VideoMAE/TimeSformer).

    Weights must be placed at configs/runtime/anomaly.yaml -> video_model.model_path.
    Without weights this adapter reports 'unavailable' loudly.
    """

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._loaded = False

    def load(self) -> None:
        if not os.path.exists(self._model_path):
            logger.warning(
                "[AnomalyVideoAdapter] Model weights not found at '%s'. "
                "Provider is UNAVAILABLE. Anomaly video model will not run.",
                self._model_path,
            )
            return
        try:
            import torch  # noqa: F401
            logger.info("[AnomalyVideoAdapter] Loading weights from '%s'", self._model_path)
            # Concrete implementation hooks here when weights are available.
            # e.g. self._model = torch.load(self._model_path, map_location=self._device)
            self._loaded = False  # set True only after successful load
            logger.warning(
                "[AnomalyVideoAdapter] Weights found but concrete model class not yet wired. "
                "Adapter is in stub mode."
            )
        except ImportError:
            logger.error("[AnomalyVideoAdapter] torch not installed — adapter unavailable.")

    def is_loaded(self) -> bool:
        return self._loaded

    def predict_clip(
        self, frames: list, metadata: dict | None = None
    ) -> AnomalyPrediction | None:
        if not self._loaded:
            logger.warning(
                "[AnomalyVideoAdapter] predict_clip called but model is not loaded. "
                "No prediction returned."
            )
            return None
        # Concrete model inference goes here.
        return None

    def health(self) -> dict:
        weights_present = os.path.exists(self._model_path)
        status = "healthy" if self._loaded else ("degraded" if weights_present else "unavailable")
        return {
            "loaded": self._loaded,
            "provider": "pretrained_video",
            "weights_present": weights_present,
            "model_path": self._model_path,
            "status": status,
        }


def build_adapter(cfg: dict) -> AnomalyModelAdapter:
    """Factory: build the appropriate adapter from anomaly config."""
    video_cfg = cfg.get("video_model", {})
    if not video_cfg.get("enabled", False):
        return RuleOnlyAdapter()

    provider = video_cfg.get("provider", "pretrained_adapter")
    model_path = video_cfg.get("model_path", "models/anomaly/current.pt")
    device = cfg.get("device", "cuda")

    if provider in ("pretrained_adapter", "pretrained_video"):
        adapter = PretrainedVideoAdapter(model_path=model_path, device=device)
    else:
        logger.warning("[AnomalyAdapter] Unknown provider '%s', falling back to rule_only.", provider)
        adapter = RuleOnlyAdapter()

    adapter.load()
    return adapter
