from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import numpy as np
from ultralytics import YOLO

from inference.monitoring.metrics import get_metrics
from inference.schemas import Detection, DetectedObject, DetectionResult, FramePacket
from ml.runtime import ModelRouter, get_best_device, system_boot_check

# TYPE_CHECKING guard avoids a circular-import at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from inference.model_pool import ModelPool

logger = logging.getLogger(__name__)

# Phone-model raw class names that should be normalised to "phone".
# Roboflow numeric exports use '0'/'1'; named exports use 'phone'/'cell phone'.
_DEVICE_RAW: frozenset[str] = frozenset({"phone", "tablet", "cell phone", "0", "1"})


def _normalize_class(raw: str, source_model: str) -> str:
    """
    Normalise raw YOLO class labels to canonical threat categories.

    Weapon sub-classes (pistol, rifle, knife, grenade, shotgun, …) are
    preserved exactly as returned by the model so that downstream engines
    (EventEngine class weights, ScenarioEngine clustering) can act on the
    full granularity.

    Phone model: Roboflow numeric export names ('0', '1') and named variants
    ('phone', 'cell phone') are all collapsed to 'phone'.
    """
    if source_model == "phone_model" or raw in _DEVICE_RAW:
        return "phone"
    # Weapon sub-classes and any other labels pass through unchanged.
    return raw


class DetectionEngine:
    """
    Unified dual-model inference engine for real-time surveillance.

    Loads weapon and phone YOLO models once at construction and merges
    their per-frame outputs into a canonical FramePacket.  Supports both
    single-frame (predict) and multi-frame batch (predict_batch) inference.
    Batch inference issues a single YOLO forward pass per model for all
    frames in the batch, yielding substantially better GPU utilisation than
    N sequential single-frame calls.

    Usage (new API):
        engine = DetectionEngine(weapon_model_path, phone_model_path)
        packet  = engine.predict(frame, frame_id=i)
        packets = engine.predict_batch(frames, frame_ids=[…])

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
            self._use_half = model_pool.use_half
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
            self._use_half: bool = self._device == "cuda"
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
        resolved = get_best_device(prefer_gpu=True)
        if resolved == "cpu":
            logger.warning(
                "CUDA not available — DetectionEngine falling back to CPU. "
                "Inference performance will be degraded."
            )
        return resolved

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
            # Explicitly place weights and cast to target dtype upfront.
            try:
                model.model.to(self._device)
                if self._use_half:
                    model.model.half()   # FP16 weights for ~2× GPU throughput
            except Exception:
                pass  # ultralytics handles device/dtype via runtime args if this fails
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

    # ── primary inference interface — single frame ────────────────────────────

    def predict(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
        camera_id: str = "default",
    ) -> FramePacket:
        """
        Run all configured models on *frame* and return a unified FramePacket.

        Detections from both models are merged; phone class names are normalised;
        weapon sub-class names are preserved at full granularity.
        """
        if not self.is_loaded:
            raise RuntimeError("DetectionEngine cannot run without weapon and phone models loaded.")

        detections: list[Detection] = []
        _t0 = time.monotonic()
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

    # ── primary inference interface — batch ───────────────────────────────────

    def predict_batch(
        self,
        frames: List[np.ndarray],
        frame_ids: List[int] | None = None,
        camera_id: str = "default",
    ) -> List[FramePacket]:
        """
        Run both models over a list of frames in two batched GPU calls and
        return one FramePacket per input frame.

        Compared to calling predict() N times, predict_batch() issues only
        two YOLO forward passes (one per model) regardless of batch size,
        dramatically reducing per-frame GPU overhead.

        Args:
            frames:    List of BGR np.ndarray images (all at the same resolution).
            frame_ids: Optional frame identifiers; defaults to [0, 1, 2, …].
            camera_id: Camera identifier attached to every Detection in the batch.

        Returns:
            List[FramePacket], one per input frame, in the same order.
        """
        if not self.is_loaded:
            raise RuntimeError("DetectionEngine cannot run without weapon and phone models loaded.")
        if not frames:
            return []
        if frame_ids is None:
            frame_ids = list(range(len(frames)))

        _t0 = time.monotonic()
        weapon_per_frame = self._run_model_batch(frames, "weapon_model", camera_id)
        phone_per_frame = self._run_model_batch(frames, "phone_model", camera_id)
        _m = get_metrics()
        _m.record_inference_time(time.monotonic() - _t0)

        packets: List[FramePacket] = []
        for i, frame in enumerate(frames):
            fid = frame_ids[i] if i < len(frame_ids) else i
            detections = weapon_per_frame[i] + phone_per_frame[i]
            _m.increment("detections_count", len(detections))
            height, width = frame.shape[:2]
            packets.append(FramePacket(
                frame_id=fid,
                detections=detections,
                camera_id=camera_id,
                frame_width=width,
                frame_height=height,
                metadata={"model_status": self.model_status},
                image=frame,
            ))

        logger.debug(json.dumps({
            "event": "predict_batch",
            "batch_size": len(frames),
            "total_detections": sum(len(p.detections) for p in packets),
            "ts": datetime.now(timezone.utc).isoformat(),
        }))
        return packets

    # ── internal inference helpers ────────────────────────────────────────────

    def _run_model(
        self,
        frame: np.ndarray,
        model: "YOLO | None",
        source_model: str,
        camera_id: str,
    ) -> list[Detection]:
        """
        Single-frame inference.  Routes through ModelPool when in pool mode.
        Reads all tensor data in one batch .tolist() call to avoid per-box
        CPU-GPU synchronisation overhead.
        """
        try:
            if self._model_pool is not None:
                if source_model == "weapon_model":
                    results = self._model_pool.run_weapon(frame)
                    names = self._model_pool.weapon_names
                else:
                    results = self._model_pool.run_phone(frame)
                    names = self._model_pool.phone_names
            else:
                results = model(frame, verbose=False, device=self._device, half=self._use_half)
                names = model.names
        except Exception as exc:
            logger.error(json.dumps({
                "event": "model_inference_error",
                "model": source_model,
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
            return []
        return self._parse_results(results, names, source_model, camera_id)

    def _run_model_batch(
        self,
        frames: List[np.ndarray],
        source_model: str,
        camera_id: str,
    ) -> List[List[Detection]]:
        """
        Batch inference for a list of frames.  Issues one YOLO forward pass for
        all frames combined.  Returns a list-of-lists: one Detection list per
        input frame, in the same order.
        """
        try:
            if self._model_pool is not None:
                if source_model == "weapon_model":
                    all_results = self._model_pool.run_weapon_batch(frames)
                    names = self._model_pool.weapon_names
                else:
                    all_results = self._model_pool.run_phone_batch(frames)
                    names = self._model_pool.phone_names
            else:
                model = (
                    self._weapon_model
                    if source_model == "weapon_model"
                    else self._phone_model
                )
                all_results = model(frames, verbose=False, device=self._device, half=self._use_half)
                names = model.names
        except Exception as exc:
            logger.error(json.dumps({
                "event": "model_batch_inference_error",
                "model": source_model,
                "batch_size": len(frames),
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
            return [[] for _ in frames]

        per_frame: List[List[Detection]] = [
            self._parse_results([r], names, source_model, camera_id)
            for r in all_results
        ]
        # Guard against YOLO returning fewer result objects than input frames
        while len(per_frame) < len(frames):
            per_frame.append([])
        return per_frame

    @staticmethod
    def _parse_results(
        results: list,
        names: dict,
        source_model: str,
        camera_id: str,
    ) -> list[Detection]:
        """Extract Detection objects from ultralytics result objects."""
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
