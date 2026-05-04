from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from inference.monitoring.metrics import get_metrics
from inference.schemas import Detection, DetectedObject, DetectionResult, FramePacket
from ml.runtime import ModelRouter, system_boot_check

# TYPE_CHECKING guard avoids a circular-import at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from inference.model_pool import ModelPool

logger = logging.getLogger(__name__)

# Class name normalisation maps
_WEAPON_RAW: frozenset[str] = frozenset(
    {"pistol", "rifle", "knife", "grenade", "shotgun", "gun", "sword"}
)
_DEVICE_RAW: frozenset[str] = frozenset({"phone", "tablet", "cell phone"})


def _normalize_class(raw: str, source_model: str) -> str:
    """
    Map raw YOLO class labels to canonical threat categories.

    Phone model note: the trained phone_detector (v1) uses numeric class names
    '0' and '1' from its Roboflow export.  Both IDs are phone-related so both
    normalise to 'phone' when the source is phone_model.
    """
    if source_model == "weapon_model" and raw in _WEAPON_RAW:
        return "weapon"
    if source_model == "phone_model":
        # Handles both named classes ("phone", "cell phone") and
        # Roboflow numeric export names ('0', '1')
        return "phone"
    if raw in _DEVICE_RAW:
        return "phone"
    return raw


class DetectionEngine:
    """
    Unified dual-model inference engine for real-time surveillance.

    Loads weapon and phone YOLO models once at construction and merges
    their per-frame outputs into a canonical FramePacket.  Maintains
    separate internal pipelines to support independent model updates.

    Usage (new API):
        engine = DetectionEngine(weapon_model_path, phone_model_path)
        packet = engine.predict(frame, frame_id=i)

    Usage (legacy API, backwards-compatible):
        engine = DetectionEngine()          # loads required weapon + phone models
        engine.load_models()                # no-op if already loaded
        result = engine.process_frame(frame, frame_id=i)
    """

    def __init__(
        self,
        weapon_model_path: str | None = None,
        phone_model_path: str | None = None,
        device: str = "auto",
        model_pool: "ModelPool | None" = None,
    ) -> None:
        system_boot_check()
        self._model_pool = model_pool

        if model_pool is not None:
            # Pool mode: borrow shared weights; no per-stream YOLO allocation.
            self._weapon_path = ""
            self._phone_path = ""
            self._device = model_pool.device
            self._weapon_model = None
            self._phone_model = None
            self._model_status = dict(model_pool.model_status)
        else:
            # Standalone mode: load private YOLO instances (original behaviour).
            router = ModelRouter()
            weapon_model = router.get_model("weapon") if weapon_model_path is None else None
            phone_model = router.get_model("phone") if phone_model_path is None else None
            self._weapon_path = weapon_model_path or weapon_model["resolved_path"]
            self._phone_path = phone_model_path or phone_model["resolved_path"]
            self._device = self._resolve_device(device)
            self._weapon_model: YOLO | None = None
            self._phone_model: YOLO | None = None
            self._model_status: dict[str, str] = {
                "weapon_model": "not_loaded",
                "phone_model": "not_loaded",
            }
            self._load_models()

    # ── initialisation ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        import torch

        if not torch.cuda.is_available():
            logger.warning(
                "CUDA not available — DetectionEngine falling back to CPU. "
                "Inference performance will be degraded."
            )
            return "cpu"
        return "cuda"

    def _load_models(self) -> None:
        self._weapon_model = self._load_one(self._weapon_path, "weapon_model")
        self._phone_model = self._load_one(self._phone_path, "phone_model")

    def _load_one(self, path: str, label: str) -> YOLO:
        ext = Path(path).suffix.lower()
        if ext not in (".pt", ".onnx"):
            self._model_status[label] = f"error: unsupported format {ext}"
            raise RuntimeError(f"{label} has unsupported format: {path}")
        try:
            model = YOLO(path)
            self._model_status[label] = "loaded"
            logger.info(json.dumps({
                "event": "model_loaded", "model": label,
                "path": path, "device": self._device,
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
            return model
        except Exception as exc:
            self._model_status[label] = f"error: {exc}"
            logger.error(json.dumps({
                "event": "model_load_error", "model": label, "error": str(exc),
            }))
            raise RuntimeError(f"Failed to load {label}: {path}") from exc

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        if self._model_pool is not None:
            return self._model_pool.is_loaded
        return self._weapon_model is not None and self._phone_model is not None

    @property
    def model_status(self) -> dict[str, str]:
        if self._model_pool is not None:
            return dict(self._model_pool.model_status)
        return dict(self._model_status)

    def load_models(self) -> None:
        """Backwards-compatible explicit load. No-op when already loaded."""
        if not self.is_loaded:
            self._load_models()

    # ── primary inference interface ───────────────────────────────────────────

    def predict(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
        camera_id: str = "default",
    ) -> FramePacket:
        """
        Run all configured models on *frame* and return a unified FramePacket.

        Detections from both models are merged; class names are normalised.
        No CPU-GPU synchronisation occurs inside this method (tensor values
        are read in a single batched .tolist() call per result set).
        """
        if not self.is_loaded:
            raise RuntimeError("DetectionEngine cannot run without weapon and phone models loaded.")

        detections: list[Detection] = []
        _t0 = time.monotonic()
        # In pool mode _weapon_model/_phone_model are None; _run_model routes via pool.
        detections.extend(self._run_model(frame, self._weapon_model, "weapon_model", camera_id))
        detections.extend(self._run_model(frame, self._phone_model, "phone_model", camera_id))
        _m = get_metrics()
        _m.record_inference_time(time.monotonic() - _t0)
        _m.increment("detections_count", len(detections))

        logger.debug(json.dumps({
            "event": "predict",
            "frame_id": frame_id,
            "n_detections": len(detections),
            "ts": datetime.now(timezone.utc).isoformat(),
        }))
        height, width = frame.shape[:2]
        return FramePacket(
            frame_id=frame_id,
            detections=detections,
            camera_id=camera_id,
            frame_width=width,
            frame_height=height,
            metadata={"model_status": self.model_status},
            image=frame,
        )

    def _run_model(
        self,
        frame: np.ndarray,
        model: "YOLO | None",
        source_model: str,
        camera_id: str,
    ) -> list[Detection]:
        """
        Single-model inference. Reads all tensor data in one batch call.

        When operating in pool mode (self._model_pool is not None) the YOLO
        call is routed through ModelPool which owns the GPU semaphore.
        """
        try:
            if self._model_pool is not None:
                # Pool path: semaphore-guarded shared inference
                if source_model == "weapon_model":
                    results = self._model_pool.run_weapon(frame)
                    names = self._model_pool.weapon_names
                else:
                    results = self._model_pool.run_phone(frame)
                    names = self._model_pool.phone_names
            else:
                # Standalone path: private YOLO instance
                results = model(frame, verbose=False, device=self._device)
                names = model.names
        except Exception as exc:
            logger.error(json.dumps({
                "event": "model_inference_error",
                "model": source_model,
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
            return []
        out: list[Detection] = []
        for r in results:
            if r.boxes is None:
                continue
            # Batch-read all box data to avoid per-box CPU-GPU sync
            boxes = r.boxes.xyxy.tolist()
            confs = r.boxes.conf.tolist()
            clses = r.boxes.cls.tolist()
            for (x1, y1, x2, y2), conf, cls_idx in zip(boxes, confs, clses):
                conf = round(float(conf), 3)
                if conf <= 0.0:
                    continue
                x1, y1, x2, y2 = round(x1), round(y1), round(x2), round(y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                raw_cls = names[int(cls_idx)]
                out.append(Detection(
                    class_name=_normalize_class(raw_cls, source_model),
                    bbox=[x1, y1, x2, y2],
                    confidence=conf,
                    source_model=source_model,
                    camera_id=camera_id,
                ))
        return out

    # ── legacy interface (backwards compatibility) ────────────────────────────

    def process_frame(self, frame: np.ndarray, frame_id: int = 0, camera_id: str = "default") -> DetectionResult:
        """Legacy single-model interface returning DetectionResult."""
        packet = self.predict(frame, frame_id, camera_id=camera_id)
        objects = [
            DetectedObject(
                type=d.class_name,
                confidence=d.confidence,
                bbox=d.bbox,
            )
            for d in packet.detections
        ]
        return DetectionResult(frame_id=frame_id, objects=objects)
