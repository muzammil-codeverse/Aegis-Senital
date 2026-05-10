from __future__ import annotations

import logging
import os

from inference.anomaly.schemas import AnomalyPrediction, AnomalyWindow

logger = logging.getLogger(__name__)

_VIOLENCE_MODEL_PATH = "models/anomaly/violence_yolo11.pt"

# Training command (documented here, not executed at runtime):
# yolo detect train `
#   model=yolo11s.pt `
#   data=datasets/training/anomaly_violence/data.yaml `
#   epochs=60 imgsz=640 batch=8 device=0 workers=4 `
#   project=runs/aegis_anomaly name=yolo11s_violence_detector patience=15


class ViolenceVisualAdapter:
    """
    YOLO11-based visual cue detector for violence/fight frames.

    This is NOT a replacement for temporal anomaly models — it is a supporting
    visual cue source. Final violence decisions are made by AnomalyService fusion.
    """

    def __init__(
        self,
        model_path: str = _VIOLENCE_MODEL_PATH,
        device: str = "cuda",
        conf_threshold: float = 0.40,
        is_production: bool = False,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._conf_threshold = conf_threshold
        self._is_production = is_production
        self._model = None
        self._loaded = False

    def load(self) -> None:
        if not os.path.exists(self._model_path):
            msg = (
                "[ViolenceAdapter] YOLO11 violence model not found at '%s'. "
                "Train it first: see training command in violence_adapter.py."
            )
            if self._is_production:
                logger.error(msg + " PRODUCTION: failing fast.", self._model_path)
                raise RuntimeError(
                    f"Violence model required in production but missing: {self._model_path}"
                )
            else:
                logger.warning(msg + " DEV: running in degraded mode.", self._model_path)
            return

        try:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
            self._model.to(self._device)
            self._loaded = True
            logger.info("[ViolenceAdapter] Loaded from '%s' on device '%s'.", self._model_path, self._device)
        except ImportError:
            logger.error("[ViolenceAdapter] ultralytics not installed — adapter unavailable.")
        except Exception as exc:
            logger.error("[ViolenceAdapter] Load failed: %s", exc)

    def is_loaded(self) -> bool:
        return self._loaded

    def score_frame(self, frame) -> float:
        """
        Run violence visual cue detection on a single frame.
        Returns a float in [0, 1] representing visual violence likelihood.
        """
        if not self._loaded or self._model is None:
            return 0.0
        try:
            results = self._model(frame, verbose=False, device=self._device)
            if not results:
                return 0.0
            scores = [
                float(box.conf)
                for r in results
                for box in (r.boxes if r.boxes is not None else [])
            ]
            return max(scores) if scores else 0.0
        except Exception as exc:
            logger.warning("[ViolenceAdapter] Inference error: %s", exc)
            return 0.0

    def predict_window(self, window: AnomalyWindow) -> AnomalyPrediction | None:
        """
        Score a temporal window by sampling frames from the window's frame refs.
        Frame refs do not carry raw pixels — caller must have attached frame data.
        """
        if not self._loaded:
            return None
        frames_with_data = [f for f in window.frames if f.get("image") is not None]
        if not frames_with_data:
            return None

        scores = [self.score_frame(f["image"]) for f in frames_with_data]
        max_score = max(scores)
        if max_score < self._conf_threshold:
            return None

        return AnomalyPrediction(
            camera_id=window.camera_id,
            anomaly_type="violence",
            score=round(max_score, 4),
            severity="high" if max_score >= 0.70 else "medium",
            confidence=round(max_score * 0.90, 4),
            source="violence_visual_adapter",
            duration_seconds=float(len(frames_with_data)),
            track_ids=[],
            evidence={"max_frame_score": round(max_score, 4), "frames_scored": len(frames_with_data)},
        )

    def health(self) -> dict:
        weights_present = os.path.exists(self._model_path)
        if self._loaded:
            status = "healthy"
        elif weights_present:
            status = "degraded"
        else:
            status = "unavailable"
        return {
            "loaded": self._loaded,
            "provider": "violence_visual",
            "weights_present": weights_present,
            "model_path": self._model_path,
            "status": status,
        }
