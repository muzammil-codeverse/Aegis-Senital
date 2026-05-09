from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from inference.segmentation.base import SegmentationAdapter
from inference.segmentation.config import SegmentationConfig, load_segmentation_config
from inference.segmentation.mask_utils import compute_bbox_area
from inference.segmentation.sam2_adapter import Sam2SegmentationAdapter
from inference.segmentation.schemas import (
    SEGMENTATION_FAILED,
    SEGMENTATION_PROVIDER_UNAVAILABLE,
    SEGMENTATION_SKIPPED,
    SEGMENTATION_SUCCESS,
    SegmentationResult,
)

logger = logging.getLogger(__name__)

_WEAPON_LABELS = frozenset({"weapon", "pistol", "rifle", "knife", "grenade", "gun", "shotgun", "sword"})
_PHONE_LABELS = frozenset({"phone", "tablet", "cell phone"})


@dataclass
class _Candidate:
    detection_id: str
    label: str
    bbox: list[float]
    confidence: float
    source_model: str
    obj: Any


class SegmentationService:
    def __init__(
        self,
        config: SegmentationConfig | dict[str, Any] | None = None,
        adapter: SegmentationAdapter | None = None,
    ) -> None:
        self.config = (
            config
            if isinstance(config, SegmentationConfig)
            else load_segmentation_config(config)
        )
        self._lock = threading.RLock()
        self._last_error: str | None = None
        self._last_latency_ms: float = 0.0
        self._last_status: str = "disabled" if not self.config.enabled else "degraded"
        self._adapter = adapter if adapter is not None else self._build_adapter()
        if self.config.enabled and self.config.auto_load:
            try:
                self.load()
            except Exception as exc:
                self._last_error = str(exc)
                self._last_status = "failed" if not self.config.fail_open else "degraded"
                if not self.config.fail_open:
                    raise

    def load(self) -> None:
        if not self.config.enabled:
            self._last_status = "disabled"
            return
        if self._adapter is None:
            self._last_error = f"unsupported segmentation provider: {self.config.provider}"
            self._last_status = "failed"
            raise RuntimeError(self._last_error)
        self._adapter.load()
        self._last_error = None
        self._last_status = "healthy"

    def unload(self) -> None:
        if self._adapter is not None:
            self._adapter.unload()
        self._last_status = "disabled" if not self.config.enabled else "degraded"

    def is_loaded(self) -> bool:
        return bool(self._adapter and self._adapter.is_loaded())

    def refine_frame(
        self,
        packet: Any,
        events: list[Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.refine(
            image=getattr(packet, "image", None),
            detections=list(getattr(packet, "detections", []) or []),
            events=events,
        )
        metadata = getattr(packet, "metadata", None)
        if isinstance(metadata, dict):
            metadata["segmentation"] = payload
        return payload

    def refine(
        self,
        *,
        image: Any,
        detections: list[Any],
        events: list[Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            payload = self._payload(status="disabled", results=[], latency_ms=0.0)
            self._attach_to_events(events, payload, [])
            return payload

        _increment_metric("segmentation_requests_total")
        started = time.monotonic()
        skipped_results: list[SegmentationResult] = []
        try:
            candidates = self._prioritize_candidates(detections, events)
            if not candidates:
                payload = self._payload(status="skipped", results=[], latency_ms=0.0)
                self._last_status = "degraded"
                self._attach_to_events(events, payload, [])
                return payload

            eligible, skipped_results = self._split_eligible(candidates)
            for skipped in skipped_results:
                _increment_metric("segmentation_skipped_total")
                self._attach_to_detection(candidates, skipped)

            if not eligible:
                latency_ms = (time.monotonic() - started) * 1000.0
                payload = self._payload(status="skipped", results=skipped_results, latency_ms=latency_ms)
                self._last_status = "degraded"
                self._attach_to_events(events, payload, skipped_results)
                return payload

            if self._adapter is None or not self._adapter.is_loaded():
                results = [
                    self._result_for_candidate(
                        candidate,
                        status=SEGMENTATION_PROVIDER_UNAVAILABLE,
                        reason=self._last_error or "segmentation provider is not loaded",
                    )
                    for candidate in eligible
                ]
                _increment_metric("segmentation_provider_unavailable_total")
                _increment_metric("segmentation_failures_total")
                latency_ms = (time.monotonic() - started) * 1000.0
                self._last_latency_ms = latency_ms
                all_results = skipped_results + results
                payload = self._payload(status="degraded", results=all_results, latency_ms=latency_ms)
                self._attach_results(candidates, all_results, events, payload=payload)
                self._last_status = "degraded"
                self._last_error = self._last_error or "segmentation provider is not loaded"
                if not self.config.fail_open:
                    raise RuntimeError(self._last_error)
                return payload

            raw_results = self._adapter.segment_boxes(
                image,
                [candidate.bbox for candidate in eligible],
                [candidate.label for candidate in eligible],
            )
            results = self._remap_results(raw_results, eligible)
            all_results = skipped_results + results
            latency_ms = (time.monotonic() - started) * 1000.0
            self._last_latency_ms = latency_ms
            self._attach_results(candidates, all_results, events)
            self._record_result_metrics(results, latency_ms)
            status = self._status_from_results(results)
            payload = self._payload(status=status, results=all_results, latency_ms=latency_ms)
            self._last_status = "healthy" if status == "success" else "degraded"
            self._last_error = None if status == "success" else self._last_error
            if status == "failed" and not self.config.fail_open:
                raise RuntimeError("segmentation failed and fail_open=false")
            return payload
        except Exception as exc:
            self._last_error = str(exc)
            self._last_status = "failed" if not self.config.fail_open else "degraded"
            _increment_metric("segmentation_failures_total")
            if not self.config.fail_open:
                raise
            latency_ms = (time.monotonic() - started) * 1000.0
            payload = self._payload(status="failed", results=skipped_results, latency_ms=latency_ms, error=str(exc))
            self._attach_to_events(events, payload, skipped_results)
            return payload

    def get_health(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {
                "enabled": False,
                "provider": self.config.provider,
                "loaded": False,
                "device": self.config.device,
                "status": "disabled",
                "last_error": None,
            }
        provider_health = self._adapter.health() if self._adapter is not None else {}
        loaded = bool(provider_health.get("loaded", self.is_loaded()))
        if loaded:
            status = "healthy"
        elif self._last_status == "failed":
            status = "failed"
        else:
            status = "degraded"
        return {
            "enabled": True,
            "provider": self.config.provider,
            "loaded": loaded,
            "device": provider_health.get("device", self.config.device),
            "status": status,
            "last_error": self._last_error or provider_health.get("last_error"),
            **{k: v for k, v in provider_health.items() if k not in {"enabled", "provider", "loaded", "device", "status", "last_error"}},
        }

    def _build_adapter(self) -> SegmentationAdapter | None:
        if not self.config.enabled:
            return None
        if self.config.provider == "sam2":
            return Sam2SegmentationAdapter(self.config)
        return None

    def _split_eligible(self, candidates: list[_Candidate]) -> tuple[list[_Candidate], list[SegmentationResult]]:
        eligible: list[_Candidate] = []
        skipped: list[SegmentationResult] = []
        for candidate in candidates:
            area = compute_bbox_area(candidate.bbox)
            if area < self.config.min_box_area_px:
                skipped.append(self._result_for_candidate(
                    candidate,
                    status=SEGMENTATION_SKIPPED,
                    reason=f"bbox area {area}px below min_box_area_px={self.config.min_box_area_px}",
                ))
                continue
            if len(eligible) >= self.config.max_masks_per_frame:
                skipped.append(self._result_for_candidate(
                    candidate,
                    status=SEGMENTATION_SKIPPED,
                    reason=f"max_masks_per_frame={self.config.max_masks_per_frame} reached",
                ))
                continue
            eligible.append(candidate)
        return eligible, skipped

    def _prioritize_candidates(self, detections: list[Any], events: list[Any] | None) -> list[_Candidate]:
        event_labels = self._high_risk_event_labels(events)
        candidates = [candidate for item in detections if (candidate := self._candidate_from_detection(item)) is not None]
        candidates.sort(key=lambda candidate: (self._priority(candidate, event_labels), -candidate.confidence))
        return candidates

    @staticmethod
    def _candidate_from_detection(item: Any) -> _Candidate | None:
        if isinstance(item, dict):
            bbox = item.get("bbox") or item.get("box")
            label = item.get("class_name") or item.get("class") or item.get("type") or item.get("label") or "object"
            detection_id = item.get("detection_id") or item.get("id")
            confidence = item.get("confidence", item.get("score", 0.0))
            source_model = item.get("source_model", item.get("source", ""))
        else:
            bbox = getattr(item, "bbox", None)
            label = getattr(item, "class_name", None) or getattr(item, "label", None) or "object"
            detection_id = getattr(item, "detection_id", None)
            confidence = getattr(item, "confidence", 0.0)
            source_model = getattr(item, "source_model", "")
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            return None
        detection_id = str(detection_id or f"det_{abs(hash(tuple(float(v) for v in bbox[:4]))) % 1_000_000:06d}")
        return _Candidate(
            detection_id=detection_id,
            label=str(label),
            bbox=[float(v) for v in bbox[:4]],
            confidence=float(confidence or 0.0),
            source_model=str(source_model or ""),
            obj=item,
        )

    @staticmethod
    def _priority(candidate: _Candidate, event_labels: set[str]) -> int:
        label = candidate.label.lower()
        source = candidate.source_model.lower()
        if label in event_labels or label in _WEAPON_LABELS:
            return 0
        if label == "person":
            return 1
        if label in _PHONE_LABELS:
            return 2
        if "open" in source or "vocab" in source:
            return 3
        return 5 if candidate.confidence < 0.30 else 4

    @staticmethod
    def _high_risk_event_labels(events: list[Any] | None) -> set[str]:
        labels: set[str] = set()
        for event in events or []:
            priority = str(_get(event, "priority_level", _get(event, "severity", ""))).upper()
            if priority not in {"HIGH", "CRITICAL"}:
                continue
            for track in _get(event, "contributing_tracks", []) or []:
                label = track.get("class_name") or track.get("type") or track.get("label")
                if label:
                    labels.add(str(label).lower())
            event_type = str(_get(event, "event_type", "")).upper()
            if "WEAPON" in event_type:
                labels.update(_WEAPON_LABELS)
        return labels

    def _remap_results(
        self,
        raw_results: list[SegmentationResult],
        candidates: list[_Candidate],
    ) -> list[SegmentationResult]:
        remapped: list[SegmentationResult] = []
        for index, candidate in enumerate(candidates):
            if index < len(raw_results):
                result = raw_results[index]
                result.detection_id = candidate.detection_id
                result.label = candidate.label
                result.bbox = list(candidate.bbox)
                result.bbox_area = compute_bbox_area(candidate.bbox)
                remapped.append(result)
            else:
                remapped.append(self._result_for_candidate(
                    candidate,
                    status=SEGMENTATION_FAILED,
                    reason="provider returned fewer masks than requested",
                ))
        return remapped

    def _result_for_candidate(
        self,
        candidate: _Candidate,
        *,
        status: str,
        reason: str | None,
    ) -> SegmentationResult:
        return SegmentationResult(
            detection_id=candidate.detection_id,
            label=candidate.label,
            bbox=list(candidate.bbox),
            mask_encoding=self.config.mask_encoding,
            mask=None,
            mask_area=0,
            bbox_area=compute_bbox_area(candidate.bbox),
            mask_confidence=None,
            refinement_status=status,
            failure_reason=reason,
        )

    def _attach_results(
        self,
        candidates: list[_Candidate],
        results: list[SegmentationResult],
        events: list[Any] | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        for result in results:
            self._attach_to_detection(candidates, result)
        payload = payload or self._payload(status=self._status_from_results(results), results=results, latency_ms=self._last_latency_ms)
        self._attach_to_events(events, payload, results)

    @staticmethod
    def _attach_to_detection(candidates: list[_Candidate], result: SegmentationResult) -> None:
        for candidate in candidates:
            if candidate.detection_id != result.detection_id:
                continue
            if isinstance(candidate.obj, dict):
                metadata = candidate.obj.setdefault("metadata", {})
                metadata["segmentation"] = result.to_dict()
                candidate.obj["segmentation"] = result.to_dict()
            else:
                metadata = getattr(candidate.obj, "metadata", None)
                if isinstance(metadata, dict):
                    metadata["segmentation"] = result.to_dict()
                try:
                    setattr(candidate.obj, "segmentation", result.to_dict())
                except Exception:
                    pass
            break

    def _attach_to_events(
        self,
        events: list[Any] | None,
        payload: dict[str, Any],
        results: list[SegmentationResult],
    ) -> None:
        if not events:
            return
        for event in events:
            event_payload = dict(payload)
            event_payload["masks"] = [result.to_event_metadata() for result in self._results_for_event(event, results)]
            event_payload["mask_count"] = sum(
                1 for result in event_payload["masks"]
                if result.get("refinement_status") == SEGMENTATION_SUCCESS
            )
            if isinstance(event, dict):
                event["segmentation"] = event_payload
                event.setdefault("metadata", {})["segmentation"] = event_payload
            else:
                try:
                    setattr(event, "segmentation", event_payload)
                except Exception:
                    pass
                metadata = getattr(event, "metadata", None)
                if isinstance(metadata, dict):
                    metadata["segmentation"] = event_payload

    @staticmethod
    def _results_for_event(event: Any, results: list[SegmentationResult]) -> list[SegmentationResult]:
        contributing = _get(event, "contributing_tracks", []) or []
        if not contributing:
            return results
        matched: list[SegmentationResult] = []
        for result in results:
            for track in contributing:
                label = str(track.get("class_name") or track.get("type") or "").lower()
                bbox = track.get("bbox") or []
                if label and label != result.label.lower():
                    continue
                if len(bbox) == 4 and _bbox_iou(result.bbox, bbox) <= 0.0:
                    continue
                matched.append(result)
                break
        return matched or results

    def _payload(
        self,
        *,
        status: str,
        results: list[SegmentationResult],
        latency_ms: float,
        error: str | None = None,
    ) -> dict[str, Any]:
        masks = [result.to_dict() for result in results]
        return {
            "enabled": self.config.enabled,
            "provider": self.config.provider,
            "status": status,
            "mask_count": sum(1 for result in results if result.refinement_status == SEGMENTATION_SUCCESS),
            "latency_ms": round(float(latency_ms), 3),
            "masks": masks,
            **({"error": error} if error else {}),
        }

    @staticmethod
    def _status_from_results(results: list[SegmentationResult]) -> str:
        if not results:
            return "skipped"
        success = sum(1 for result in results if result.refinement_status == SEGMENTATION_SUCCESS)
        failed = sum(1 for result in results if result.refinement_status in {SEGMENTATION_FAILED, SEGMENTATION_PROVIDER_UNAVAILABLE})
        if success and failed == 0:
            return "success"
        if success:
            return "degraded"
        if all(result.refinement_status == SEGMENTATION_SKIPPED for result in results):
            return "skipped"
        return "failed"

    @staticmethod
    def _record_result_metrics(results: list[SegmentationResult], latency_ms: float) -> None:
        successes = [result for result in results if result.refinement_status == SEGMENTATION_SUCCESS]
        failures = [result for result in results if result.refinement_status in {SEGMENTATION_FAILED, SEGMENTATION_PROVIDER_UNAVAILABLE}]
        skipped = [result for result in results if result.refinement_status == SEGMENTATION_SKIPPED]
        if successes:
            _increment_metric("segmentation_success_total")
            _increment_metric("segmentation_masks_generated_total", len(successes))
            ratios = [
                result.mask_area / result.bbox_area
                for result in successes
                if result.bbox_area > 0
            ]
            if ratios:
                _record_metric_value("segmentation_mask_area_ratio", sum(ratios) / len(ratios))
        if failures:
            _increment_metric("segmentation_failures_total")
            if any(result.refinement_status == SEGMENTATION_PROVIDER_UNAVAILABLE for result in failures):
                _increment_metric("segmentation_provider_unavailable_total")
        if skipped:
            _increment_metric("segmentation_skipped_total", len(skipped))
        _record_metric_value("segmentation_latency_ms", latency_ms)


def _increment_metric(counter: str, value: int = 1) -> None:
    for getter in _metric_getters():
        try:
            getter().increment(counter, value)
        except Exception:
            pass


def _record_metric_value(counter: str, value: float) -> None:
    for getter in _metric_getters():
        try:
            metrics = getter()
            if hasattr(metrics, "record_segmentation_value"):
                metrics.record_segmentation_value(counter, value)
            elif hasattr(metrics, "set_value"):
                metrics.set_value(counter, value)
            else:
                setattr(metrics, counter, value)
        except Exception:
            pass


def _metric_getters() -> list[Any]:
    getters: list[Any] = []
    try:
        from inference.monitoring.metrics import get_metrics as get_monitoring_metrics

        getters.append(get_monitoring_metrics)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as core_metrics

        getters.append(lambda: core_metrics)
    except Exception:
        pass
    return getters


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _bbox_iou(left: list[float], right: list[float]) -> float:
    if len(left) < 4 or len(right) < 4:
        return 0.0
    xi1, yi1 = max(left[0], right[0]), max(left[1], right[1])
    xi2, yi2 = min(left[2], right[2]), min(left[3], right[3])
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    area_l = compute_bbox_area(left)
    area_r = compute_bbox_area(right)
    union = area_l + area_r - inter
    return float(inter / union) if union > 0 else 0.0


_service: SegmentationService | None = None
_service_lock = threading.Lock()


def get_segmentation_service(config: dict[str, Any] | None = None) -> SegmentationService:
    global _service
    if _service is None or config is not None:
        with _service_lock:
            if _service is None or config is not None:
                _service = SegmentationService(config=config)
    return _service
