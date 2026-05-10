from __future__ import annotations

import logging
import threading
import time

from inference.anomaly.config import load_anomaly_config
from inference.anomaly.pretrained_adapter import AnomalyModelAdapter, build_adapter
from inference.anomaly.rule_engine import RuleEngine
from inference.anomaly.schemas import AnomalyPrediction, AnomalyWindow
from inference.anomaly.scoring import fuse_predictions
from inference.anomaly.temporal_buffer import TemporalBuffer
from inference.anomaly.violence_adapter import ViolenceVisualAdapter

logger = logging.getLogger(__name__)


class AnomalyService:
    """
    Orchestrator for the Phase 28 anomaly detection subsystem.

    Flow per frame:
        add_frame() → temporal buffer → (per window_seconds) rule engine
        → optional model adapters → score fusion → AnomalyPrediction list

    Fail-open: if the service encounters an error and fail_open=true, it
    returns an empty list rather than raising.
    """

    def __init__(self, is_production: bool = False) -> None:
        self._cfg = load_anomaly_config()
        self._enabled = bool(self._cfg.get("enabled", True))
        self._fail_open = bool(self._cfg.get("fail_open", True))
        self._is_production = is_production
        self._window_seconds = float(self._cfg.get("temporal_window_seconds", 5))
        self._sample_rate = int(self._cfg.get("frame_sample_rate", 5))
        self._fusion_weights = self._cfg.get("fusion", {}).get("weights", {})
        self._fusion_thresholds = self._cfg.get("fusion", {}).get("thresholds", {})

        self._buffer = TemporalBuffer(
            window_seconds=self._window_seconds,
            sample_rate=self._sample_rate,
        )
        self._rule_engine = RuleEngine()
        self._model_adapter: AnomalyModelAdapter = build_adapter(self._cfg)
        self._violence_adapter = ViolenceVisualAdapter(
            device=self._cfg.get("device", "cuda"),
            is_production=is_production,
        )

        # Load violence adapter (non-fatal if missing in dev)
        try:
            self._violence_adapter.load()
        except RuntimeError:
            if not self._fail_open:
                raise

        self._status = "healthy" if self._enabled else "disabled"
        self._last_error: str | None = None
        self._lock = threading.RLock()

        # Track last window evaluation time per camera
        self._last_eval: dict[str, float] = {}

        logger.info(
            "[AnomalyService] Initialised — enabled=%s fail_open=%s window=%.1fs "
            "model_adapter=%s violence_loaded=%s",
            self._enabled,
            self._fail_open,
            self._window_seconds,
            self._model_adapter.__class__.__name__,
            self._violence_adapter.is_loaded(),
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_frame(
        self,
        camera_id: str,
        frame_id: int,
        timestamp: float,
        detections: list[dict],
        tracks: list[dict],
        segmentation: dict | None = None,
    ) -> list[AnomalyPrediction]:
        """
        Ingest one frame. Returns anomaly predictions if a temporal window
        evaluation fires, otherwise returns [].
        """
        if not self._enabled:
            return []
        try:
            self._buffer.add_frame(
                camera_id=camera_id,
                frame_id=frame_id,
                timestamp=timestamp,
                detections=detections,
                tracks=tracks,
                segmentation=segmentation,
            )
            now = time.time()
            with self._lock:
                last = self._last_eval.get(camera_id, 0.0)
                if now - last < self._window_seconds:
                    return []
                self._last_eval[camera_id] = now

            window = self._buffer.get_window(camera_id)
            if window is None:
                return []
            return self._evaluate_window(window)
        except Exception as exc:
            self._last_error = str(exc)
            self._status = "degraded"
            logger.error("[AnomalyService] Error in add_frame: %s", exc)
            if self._fail_open:
                return []
            raise

    def evaluate_window(self, window: AnomalyWindow) -> list[AnomalyPrediction]:
        """Directly evaluate a pre-built window (used in tests / benchmark)."""
        return self._evaluate_window(window)

    def health(self) -> dict:
        return {
            "enabled": self._enabled,
            "rule_engine_loaded": True,
            "model_loaded": self._model_adapter.is_loaded(),
            "violence_adapter_loaded": self._violence_adapter.is_loaded(),
            "provider": self._model_adapter.__class__.__name__,
            "status": self._status,
            "last_error": self._last_error,
            "buffer_sizes": self._buffer.buffer_sizes(),
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _evaluate_window(self, window: AnomalyWindow) -> list[AnomalyPrediction]:
        t0 = time.perf_counter()
        try:
            rule_preds = self._rule_engine.evaluate(window)

            model_pred: AnomalyPrediction | None = None
            if self._model_adapter.is_loaded():
                model_pred = self._model_adapter.predict_clip(
                    frames=window.frames, metadata=window.to_dict()
                )

            violence_pred: AnomalyPrediction | None = None
            if self._violence_adapter.is_loaded():
                violence_pred = self._violence_adapter.predict_window(window)

            fused = fuse_predictions(
                rule_predictions=rule_preds,
                model_prediction=model_pred,
                violence_prediction=violence_pred,
                weights=self._fusion_weights,
                thresholds=self._fusion_thresholds,
            )

            if self._status == "degraded" and not self._last_error:
                self._status = "healthy"

            latency_ms = (time.perf_counter() - t0) * 1000.0
            if latency_ms > 120.0:
                logger.warning(
                    "[AnomalyService] Window evaluation latency %.1fms exceeds 120ms target.",
                    latency_ms,
                )

            return fused
        except Exception as exc:
            self._last_error = str(exc)
            self._status = "degraded"
            logger.error("[AnomalyService] Window evaluation error: %s", exc)
            if self._fail_open:
                return []
            raise


# ── Module-level singleton ─────────────────────────────────────────────────────

_service: AnomalyService | None = None
_service_lock = threading.Lock()


def get_anomaly_service(is_production: bool = False) -> AnomalyService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = AnomalyService(is_production=is_production)
    return _service
