from __future__ import annotations
import logging
from typing import Any

from .adapter_base import OpenVocabDetectorAdapter

logger = logging.getLogger(__name__)


class GroundingDINOAdapter(OpenVocabDetectorAdapter):
    """
    Adapter for Grounding DINO via HuggingFace Transformers.
    All imports are lazy — app startup never fails if transformers/torch absent.
    If weights unavailable and download disabled, adapter stays unavailable.
    No fake detections are generated.
    """

    PROVIDER = "grounding_dino"

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        self._model = None
        self._processor = None
        self._loaded = False
        self._unavailable_reason: str | None = None
        self._device = "cpu"

    def set_config_override(self, config_override: dict) -> None:
        """
        Merge the given override dict into the adapter config before loading.

        This allows the hot-load API to inject runtime paths (local_model_path,
        local_processor_path, device_preference) without replacing the full config.
        """
        import copy
        merged = copy.deepcopy(self._config)
        model_section = merged.setdefault("model", {})
        for key, value in config_override.items():
            model_section[key] = value
        self._config = merged

    def load(self) -> None:
        model_cfg = self._config.get("model", {})
        local_model_path = model_cfg.get("local_model_path")
        local_processor_path = model_cfg.get("local_processor_path")
        device_pref = model_cfg.get("device_preference", "cuda")

        try:
            import torch
            self._device = "cuda" if (device_pref == "cuda" and torch.cuda.is_available()) else "cpu"
        except ImportError:
            self._device = "cpu"

        try:
            from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        except ImportError as e:
            self._unavailable_reason = f"transformers not installed: {e}"
            logger.warning("GroundingDINO unavailable: %s", self._unavailable_reason)
            return

        model_id = local_model_path or model_cfg.get("model_id", "IDEA-Research/grounding-dino-base")
        processor_id = local_processor_path or model_id

        # If no local path and download not explicitly allowed, stay unavailable
        if not local_model_path:
            allow_download = self._config.get("allow_huggingface_download", False)
            if not allow_download:
                self._unavailable_reason = (
                    "local_model_path not configured and allow_huggingface_download is false"
                )
                logger.info("GroundingDINO: %s", self._unavailable_reason)
                return

        try:
            self._processor = AutoProcessor.from_pretrained(processor_id)
            self._model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
            if self._device == "cuda":
                self._model = self._model.to("cuda")
            self._model.eval()
            self._loaded = True
            logger.info("GroundingDINO loaded on %s", self._device)
        except Exception as e:
            self._unavailable_reason = f"Failed to load model: {e}"
            self._loaded = False
            self._model = None
            self._processor = None
            logger.warning("GroundingDINO load failed: %s", self._unavailable_reason)

    def is_available(self) -> bool:
        return self._loaded and self._model is not None

    def get_status(self) -> dict:
        return {
            "available": self.is_available(),
            "provider": self.PROVIDER,
            "model_id": self._config.get("model", {}).get("model_id", "grounding_dino_base"),
            "device": self._device if self.is_available() else None,
            "reason": self._unavailable_reason if not self.is_available() else None,
        }

    def detect(
        self,
        image: Any,
        prompts: list[str],
        thresholds: dict | None = None,
    ) -> list[dict]:
        if not self.is_available():
            return []

        thresholds = thresholds or {}
        box_threshold = thresholds.get("box_threshold", 0.35)
        text_threshold = thresholds.get("text_threshold", 0.25)

        # Build prompt string: ". " separated
        prompt_text = ". ".join(p.strip().rstrip(".") for p in prompts if p.strip())
        if not prompt_text:
            return []

        try:
            import torch
            from PIL import Image as PILImage
            import numpy as np

            if isinstance(image, str):
                pil_image = PILImage.open(image).convert("RGB")
            elif isinstance(image, np.ndarray):
                pil_image = PILImage.fromarray(image)
            elif hasattr(image, "convert"):
                pil_image = image.convert("RGB")
            else:
                logger.warning("GroundingDINO: unsupported image type %s", type(image))
                return []

            inputs = self._processor(images=pil_image, text=prompt_text, return_tensors="pt")
            if self._device == "cuda":
                inputs = {k: v.to("cuda") for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)

            width, height = pil_image.size
            results = self._processor.post_process_grounded_object_detection(
                outputs,
                inputs["input_ids"],
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                target_sizes=[(height, width)],
            )

            detections = []
            if results:
                result = results[0]
                boxes = result.get("boxes", [])
                scores = result.get("scores", [])
                labels = result.get("labels", [])
                for box, score, label in zip(boxes, scores, labels):
                    box_list = [round(float(v), 4) for v in box.tolist()]
                    detections.append({
                        "label": str(label),
                        "confidence": round(float(score), 4),
                        "bbox": box_list,
                        "source_model": self.PROVIDER,
                    })
            return detections

        except Exception as e:
            logger.error("GroundingDINO detection error: %s", e)
            return []

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._loaded = False
        logger.info("GroundingDINO unloaded")
