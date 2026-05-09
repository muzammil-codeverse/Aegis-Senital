"""Phase 26 — Ultralytics YOLO detection adapter for benchmark evaluation."""
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


class YOLOInferenceAdapter(DetectionModelAdapter):
    """
    Ultralytics YOLO adapter.

    - Does NOT download weights. Raises FileNotFoundError if path missing.
    - Supports cuda and cpu.
    - Normalizes boxes to [x1,y1,x2,y2] absolute pixels.
    - Records per-image latency via perf_counter.
    """

    def __init__(
        self,
        model_path: str,
        name: str,
        device: str = "cpu",
        class_names: list[str] | None = None,
        version: str | None = None,
        image_size: int = 640,
    ) -> None:
        self._model_path = model_path
        self._name = name
        self._device = device
        self._class_names = class_names or []
        self._version = version
        self._image_size = image_size
        self._model = None

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str | None:
        return self._version

    @property
    def device(self) -> str:
        return self._device

    def load(self) -> None:
        path = Path(self._model_path)
        if not path.exists():
            raise FileNotFoundError(
                f"YOLO weights not found at '{self._model_path}'. "
                "Set the correct path in evaluation.yaml. "
                "Weight downloads are disabled (allow_weight_downloads: false)."
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "ultralytics package required for YOLO inference. "
                "Install with: pip install ultralytics"
            ) from exc

        t0 = time.perf_counter()
        self._model = YOLO(str(path))
        load_ms = (time.perf_counter() - t0) * 1000
        logger.info("Loaded YOLO model '%s' in %.0f ms on %s", self._name, load_ms, self._device)

    def is_loaded(self) -> bool:
        return self._model is not None

    def warmup(self, image_size: int = 640, n: int = 3) -> None:
        if not self.is_loaded():
            return
        try:
            import numpy as np
            dummy = np.zeros((image_size, image_size, 3), dtype=np.uint8)
            for _ in range(n):
                self._model.predict(dummy, device=self._device, verbose=False, imgsz=image_size)
        except Exception as exc:
            logger.debug("YOLO warmup skipped: %s", exc)

    def predict(self, image_path: str, confidence_threshold: float = 0.25) -> DetectionPrediction:
        if not self.is_loaded():
            return DetectionPrediction(
                sample_id=Path(image_path).stem,
                model_name=self._name,
                device=self._device,
                error="Model not loaded — call load() first",
            )

        path = Path(image_path)
        if not path.exists():
            return DetectionPrediction(
                sample_id=path.stem,
                model_name=self._name,
                device=self._device,
                error=f"Image file not found: {image_path}",
            )

        t0 = time.perf_counter()
        try:
            results = self._model.predict(
                str(path),
                device=self._device,
                conf=confidence_threshold,
                verbose=False,
                imgsz=self._image_size,
            )
        except Exception as exc:
            return DetectionPrediction(
                sample_id=path.stem,
                model_name=self._name,
                device=self._device,
                latency_ms=round((time.perf_counter() - t0) * 1000, 3),
                error=str(exc),
            )

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)
        detections: list[DetectionBox] = []
        img_w = img_h = 0

        result = results[0] if results else None
        if result is not None:
            if result.orig_shape:
                img_h, img_w = result.orig_shape[:2]
            if result.boxes is not None:
                boxes_xyxy = result.boxes.xyxy.cpu().numpy()
                confs = result.boxes.conf.cpu().numpy()
                cls_ids = result.boxes.cls.cpu().numpy().astype(int)
                for xyxy, conf, cls_id in zip(boxes_xyxy, confs, cls_ids):
                    label = (
                        self._class_names[cls_id]
                        if cls_id < len(self._class_names)
                        else str(cls_id)
                    )
                    detections.append(DetectionBox(
                        bbox=[float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])],
                        score=float(conf),
                        class_id=int(cls_id),
                        label=label,
                    ))

        return DetectionPrediction(
            sample_id=path.stem,
            detections=detections,
            latency_ms=latency_ms,
            model_name=self._name,
            model_version=self._version,
            device=self._device,
            image_width=img_w,
            image_height=img_h,
        )

    def unload(self) -> None:
        self._model = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        logger.info("Unloaded YOLO model '%s'", self._name)
