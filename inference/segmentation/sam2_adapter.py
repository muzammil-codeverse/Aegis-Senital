from __future__ import annotations

import importlib.util
import logging
import time
from typing import Any

import numpy as np

from inference.segmentation.base import SegmentationAdapter
from inference.segmentation.config import SegmentationConfig
from inference.segmentation.mask_utils import (
    compute_bbox_area,
    compute_mask_area,
    mask_to_polygon,
    mask_to_rle,
)
from inference.segmentation.schemas import (
    SEGMENTATION_FAILED,
    SEGMENTATION_PROVIDER_UNAVAILABLE,
    SEGMENTATION_SUCCESS,
    SegmentationResult,
)

logger = logging.getLogger(__name__)


class Sam2SegmentationAdapter(SegmentationAdapter):
    """SAM2 segmentation via Ultralytics (sam2_t.pt / sam2_s.pt).

    Uses ultralytics.SAM rather than the standalone Facebook sam2 package.
    Model auto-downloads on first use via Ultralytics asset hub.
    """

    def __init__(self, config: SegmentationConfig | None = None) -> None:
        self.config = config or SegmentationConfig()
        self._model: Any | None = None
        self._loaded = False
        self._last_error: str | None = None
        self._last_latency_ms: float = 0.0
        self._device = self.config.device

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def device(self) -> str:
        return self._device

    def load(self) -> None:
        try:
            from ultralytics import SAM
        except ImportError as exc:
            self._last_error = "ultralytics not installed"
            raise RuntimeError(self._last_error) from exc

        self._device = self._resolve_device(self.config.device)

        # Prefer absolute checkpoint path from config; fall back to Ultralytics auto-download.
        checkpoint = self.config.sam2.checkpoint
        model_path = str(checkpoint) if checkpoint.exists() else "sam2_t.pt"

        try:
            self._model = SAM(model_path)
            self._loaded = True
            self._last_error = None
            logger.info("SAM2 adapter loaded via Ultralytics (%s) on %s", model_path, self._device)
        except Exception as exc:
            self._loaded = False
            self._model = None
            self._last_error = f"SAM2 load failed: {exc}"
            raise RuntimeError(self._last_error) from exc

    def unload(self) -> None:
        self._model = None
        self._loaded = False
        try:
            import torch
            if self._device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def is_loaded(self) -> bool:
        return self._loaded and self._model is not None

    def segment_boxes(
        self,
        image: Any,
        boxes: list[list[float]],
        labels: list[str] | None = None,
    ) -> list[SegmentationResult]:
        labels = labels or []
        if not self.is_loaded():
            reason = self._last_error or "SAM2 provider is not loaded"
            return [
                self._empty_result(
                    index=i,
                    bbox=box,
                    label=labels[i] if i < len(labels) else "object",
                    status=SEGMENTATION_PROVIDER_UNAVAILABLE,
                    reason=reason,
                )
                for i, box in enumerate(boxes)
            ]
        if image is None:
            return [
                self._empty_result(
                    index=i,
                    bbox=box,
                    label=labels[i] if i < len(labels) else "object",
                    status=SEGMENTATION_FAILED,
                    reason="image unavailable",
                )
                for i, box in enumerate(boxes)
            ]

        t0 = time.monotonic()
        results: list[SegmentationResult] = []
        try:
            rgb = _to_rgb_array(image)
            sam_results = self._model(rgb, bboxes=boxes, verbose=False)
            masks_data = sam_results[0].masks if sam_results else None
            for index, box in enumerate(boxes):
                label = labels[index] if index < len(labels) else "object"
                results.append(self._segment_one_from_results(index, box, label, masks_data))
        except Exception as exc:
            self._last_error = f"SAM2 segmentation failed: {exc}"
            results = [
                self._empty_result(
                    index=i,
                    bbox=box,
                    label=labels[i] if i < len(labels) else "object",
                    status=SEGMENTATION_FAILED,
                    reason=self._last_error,
                )
                for i, box in enumerate(boxes)
            ]
        finally:
            self._last_latency_ms = (time.monotonic() - t0) * 1000.0
        return results

    def health(self) -> dict[str, Any]:
        checkpoint = self.config.sam2.checkpoint
        model_config = self.config.sam2.config_path
        dependency_available = importlib.util.find_spec("ultralytics") is not None
        if not self.config.enabled:
            status = "disabled"
        elif self.is_loaded():
            status = "healthy"
        else:
            status = "degraded"
        return {
            "enabled": self.config.enabled,
            "provider": "sam2-ultralytics",
            "loaded": self.is_loaded(),
            "device": self._device,
            "status": status,
            "last_error": self._last_error,
            "dependency_available": dependency_available,
            "checkpoint_exists": checkpoint.exists(),
            "config_exists": model_config.exists(),
            "checkpoint_path": str(checkpoint),
            "model_config": str(model_config),
            "last_latency_ms": round(self._last_latency_ms, 3),
        }

    def _segment_one_from_results(
        self,
        index: int,
        box: list[float],
        label: str,
        masks_data: Any,
    ) -> SegmentationResult:
        try:
            if masks_data is None or not hasattr(masks_data, "data") or index >= len(masks_data.data):
                return self._empty_result(
                    index=index, bbox=box, label=label,
                    status=SEGMENTATION_FAILED, reason="SAM2 returned no mask",
                )
            mask_tensor = masks_data.data[index]
            mask = mask_tensor.cpu().numpy().astype(np.uint8)
            try:
                score = float(masks_data.conf[index]) if masks_data.conf is not None else None
            except Exception:
                score = None
            if self.config.mask_encoding == "polygon":
                encoded: dict | list | None = mask_to_polygon(mask)
            else:
                encoded = mask_to_rle(mask)
            return SegmentationResult(
                detection_id=f"det_{index:03d}",
                label=label,
                bbox=[float(v) for v in box[:4]],
                mask_encoding=self.config.mask_encoding,
                mask=encoded,
                mask_area=compute_mask_area(mask),
                bbox_area=compute_bbox_area(box),
                mask_confidence=score,
                refinement_status=SEGMENTATION_SUCCESS,
            )
        except Exception as exc:
            return self._empty_result(
                index=index, bbox=box, label=label,
                status=SEGMENTATION_FAILED, reason=str(exc),
            )

    def _empty_result(
        self,
        *,
        index: int,
        bbox: list[float],
        label: str,
        status: str,
        reason: str | None,
    ) -> SegmentationResult:
        return SegmentationResult(
            detection_id=f"det_{index:03d}",
            label=label,
            bbox=[float(v) for v in bbox[:4]],
            mask_encoding=self.config.mask_encoding,
            mask=None,
            mask_area=0,
            bbox_area=compute_bbox_area(bbox),
            mask_confidence=None,
            refinement_status=status,
            failure_reason=reason,
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        requested = (device or "cpu").lower()
        if requested == "auto":
            requested = "cuda"
        if requested != "cuda":
            return requested
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        raise RuntimeError("CUDA requested for SAM2 but CUDA is unavailable")


def _to_rgb_array(image: Any) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        return arr[:, :, :3][:, :, ::-1].copy()
    return arr
