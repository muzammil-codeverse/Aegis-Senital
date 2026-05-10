from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

from inference.anomaly.schemas import AnomalyPrediction, AnomalyWindow

logger = logging.getLogger(__name__)

PROVIDERS = ("rule_only", "pretrained", "pretrained_video", "violence_visual", "custom_clip_model")

# Label index that signals anomaly output from binary-trained VideoMAE.
# Index 0 = normal, 1 = anomaly (standard binary training convention).
ANOMALY_LABEL_INDEX = 1


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
    VideoMAE-based video anomaly detection adapter.

    Expects a transformers VideoMAEForVideoClassification model at model_path.
    Accepts 16-frame clips at 224x224 and returns a binary anomaly score.

    Falls back gracefully if weights or transformers are unavailable.
    """

    # VideoMAE base processor used when no local preprocessor config exists
    _FALLBACK_PROCESSOR_ID = "MCG-NJU/videomae-base"
    _NUM_FRAMES = 16
    _IMAGE_SIZE = 224

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self._model_path = model_path
        self._device = device
        self._model = None
        self._processor = None
        self._loaded = False
        self._num_classes: int = 2

    def load(self) -> None:
        if not os.path.exists(self._model_path):
            logger.warning(
                "[AnomalyVideoAdapter] Model weights not found at '%s'. "
                "Adapter is UNAVAILABLE.",
                self._model_path,
            )
            return

        safetensors = [
            f for f in os.listdir(self._model_path)
            if f.endswith(".safetensors") or f.endswith(".bin")
        ]
        if not safetensors:
            logger.warning(
                "[AnomalyVideoAdapter] No weight files in '%s'. Adapter UNAVAILABLE.",
                self._model_path,
            )
            return

        try:
            import torch
            from transformers import VideoMAEForVideoClassification, AutoImageProcessor
        except Exception as exc:
            logger.error("[AnomalyVideoAdapter] Required runtime import failed: %s", exc)
            return

        # Resolve device
        self._device = "cuda" if (self._device == "cuda" and torch.cuda.is_available()) else "cpu"

        # Check available VRAM before loading to avoid OOM crashes
        if self._device == "cuda":
            free_bytes = torch.cuda.mem_get_info()[0]
            required_bytes = 400 * 1024 * 1024  # ~400MB for VideoMAE
            if free_bytes < required_bytes:
                logger.warning(
                    "[AnomalyVideoAdapter] Insufficient free VRAM (%.0fMB free, %.0fMB needed). "
                    "Skipping load to avoid OOM. Adapter will run rule_only.",
                    free_bytes / 1024 / 1024,
                    required_bytes / 1024 / 1024,
                )
                return

        # Load processor — prefer local, fall back to base repo if absent
        try:
            self._processor = AutoImageProcessor.from_pretrained(
                self._model_path, local_files_only=True
            )
            logger.info("[AnomalyVideoAdapter] Processor loaded from local path")
        except Exception:
            logger.info(
                "[AnomalyVideoAdapter] No local processor config — using %s",
                self._FALLBACK_PROCESSOR_ID,
            )
            try:
                self._processor = AutoImageProcessor.from_pretrained(self._FALLBACK_PROCESSOR_ID)
            except Exception as exc:
                logger.warning(
                    "[AnomalyVideoAdapter] Could not load processor (%s). "
                    "Will use manual preprocessing.",
                    exc,
                )
                self._processor = None

        # Load model weights
        try:
            self._model = VideoMAEForVideoClassification.from_pretrained(
                self._model_path,
                local_files_only=True,
                ignore_mismatched_sizes=True,
            )
            self._model = self._model.to(self._device)
            self._model.eval()
            self._num_classes = self._model.config.num_labels if hasattr(self._model.config, "num_labels") else 2
            self._loaded = True
            logger.info(
                "[AnomalyVideoAdapter] VideoMAE loaded on %s — %d classes",
                self._device, self._num_classes,
            )
        except Exception as exc:
            logger.error("[AnomalyVideoAdapter] Failed to load model: %s", exc)
            self._model = None
            self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded and self._model is not None

    def predict_clip(
        self, frames: list, metadata: dict | None = None
    ) -> AnomalyPrediction | None:
        if not self.is_loaded():
            return None
        if not frames:
            return None

        # If frames are metadata dicts (no raw pixels), skip model inference.
        # The temporal buffer only stores frame references; raw-pixel inference
        # requires a separate image-frame channel.
        if frames and isinstance(frames[0], dict) and "frame_id" in frames[0]:
            return None

        try:
            import torch
            import numpy as np
            from inference.anomaly.scoring import severity_from_score

            clip = self._prepare_clip(frames)
            if clip is None:
                return None

            with torch.no_grad():
                outputs = self._model(pixel_values=clip)
                logits = outputs.logits  # (1, num_classes)
                probs = torch.softmax(logits, dim=-1)[0]

            # Binary: index 1 = anomaly; multi-class: max non-normal
            if self._num_classes == 2:
                anomaly_score = float(probs[ANOMALY_LABEL_INDEX].item())
            else:
                anomaly_score = float(probs[1:].max().item())

            camera_id = (metadata or {}).get("camera_id", "unknown")
            severity = severity_from_score(anomaly_score)
            return AnomalyPrediction(
                camera_id=camera_id,
                anomaly_type="generic",
                score=anomaly_score,
                severity=severity,
                confidence=anomaly_score,
                source="pretrained_video",
                duration_seconds=float((metadata or {}).get("window_seconds", 5.0)),
                evidence={"num_frames": len(frames), "model_path": self._model_path},
            )

        except Exception as exc:
            logger.error("[AnomalyVideoAdapter] predict_clip error: %s", exc)
            return None

    def _prepare_clip(self, frames: list):
        """Preprocess a list of frames into a (1, T, C, H, W) tensor."""
        try:
            import torch
            import numpy as np
            from PIL import Image as PILImage

            # Sample or pad to NUM_FRAMES
            N = self._NUM_FRAMES
            if len(frames) >= N:
                indices = np.linspace(0, len(frames) - 1, N, dtype=int)
                sampled = [frames[i] for i in indices]
            else:
                sampled = frames + [frames[-1]] * (N - len(frames))

            pil_frames = []
            for f in sampled:
                if isinstance(f, np.ndarray):
                    pil_frames.append(PILImage.fromarray(f).resize(
                        (self._IMAGE_SIZE, self._IMAGE_SIZE)
                    ))
                elif hasattr(f, "resize"):
                    pil_frames.append(f.resize((self._IMAGE_SIZE, self._IMAGE_SIZE)))
                else:
                    pil_frames.append(PILImage.fromarray(np.zeros(
                        (self._IMAGE_SIZE, self._IMAGE_SIZE, 3), dtype=np.uint8
                    )))

            if self._processor is not None:
                inputs = self._processor(images=pil_frames, return_tensors="pt")
                pixel_values = inputs["pixel_values"].to(self._device)
            else:
                # Manual IMAGENET normalization
                mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
                tensor_frames = []
                for pil in pil_frames:
                    arr = np.array(pil, dtype=np.float32) / 255.0
                    arr = (arr - mean) / std
                    tensor_frames.append(torch.from_numpy(arr).permute(2, 0, 1))
                # (T, C, H, W) → (1, C, T, H, W)  [VideoMAE expects (B, C, T, H, W)]
                stacked = torch.stack(tensor_frames, dim=0)          # (T, C, H, W)
                stacked = stacked.permute(1, 0, 2, 3).unsqueeze(0)  # (1, C, T, H, W)
                pixel_values = stacked.to(self._device)

            return pixel_values

        except Exception as exc:
            logger.error("[AnomalyVideoAdapter] Frame prep error: %s", exc)
            return None

    def health(self) -> dict:
        weights_present = os.path.exists(self._model_path)
        status = "healthy" if self._loaded else ("degraded" if weights_present else "unavailable")
        return {
            "loaded": self._loaded,
            "provider": "pretrained_video",
            "weights_present": weights_present,
            "model_path": self._model_path,
            "device": self._device if self._loaded else None,
            "num_classes": self._num_classes if self._loaded else None,
            "status": status,
        }


def build_adapter(cfg: dict) -> AnomalyModelAdapter:
    """Factory: build the appropriate adapter from anomaly config."""
    video_cfg = cfg.get("video_model", {})
    if not video_cfg.get("enabled", False):
        return RuleOnlyAdapter()

    provider = video_cfg.get("provider", "pretrained")
    model_path = video_cfg.get("model_path", "models/anomaly/current")
    device = cfg.get("device", "cuda")

    if provider in ("pretrained", "pretrained_adapter", "pretrained_video"):
        adapter = PretrainedVideoAdapter(model_path=model_path, device=device)
    else:
        logger.warning("[AnomalyAdapter] Unknown provider '%s', falling back to rule_only.", provider)
        adapter = RuleOnlyAdapter()

    adapter.load()
    return adapter
