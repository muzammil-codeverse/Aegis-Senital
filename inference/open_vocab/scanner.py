from __future__ import annotations
import logging
import threading
import time
import uuid
from typing import Any

from .adapter_base import OpenVocabDetectorAdapter
from .result_store import OpenVocabResultStore
from .prompt_library import OpenVocabPromptLibrary
from .grounding_dino_adapter import GroundingDINOAdapter

logger = logging.getLogger(__name__)

SEVERITY_WEIGHTS = {"low": 0.25, "medium": 0.5, "high": 0.8, "critical": 1.0}


class OpenVocabThreatScanner:
    """
    Open-vocabulary threat scanner. Does not replace YOLO.
    Degrades gracefully if adapter unavailable.
    No fake detections.
    """

    def __init__(self, config: dict | None = None, event_bus=None):
        self._config = config or {}
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._active_scans = 0

        scan_policy = self._config.get("scan_policy", {})
        self._max_concurrent = scan_policy.get("max_concurrent_scans", 2)
        self._cooldown = scan_policy.get("cooldown_seconds_per_camera", 5)
        self._timeout = scan_policy.get("scan_timeout_seconds", 15)
        self._run_on_high_risk = scan_policy.get("run_on_high_risk_frames", True)
        self._run_on_incident = scan_policy.get("run_on_incident_frames", True)
        self._high_risk_threshold = self._config.get("thresholds", {}).get("high_risk_threshold", 0.55)
        self._max_detections = self._config.get("thresholds", {}).get("max_detections_per_frame", 20)

        self._camera_last_scan: dict[str, float] = {}

        self._adapter: OpenVocabDetectorAdapter = self._build_adapter()
        self._prompt_library = OpenVocabPromptLibrary(config=self._config)
        self._prompt_library.load_from_config()
        self._result_store = OpenVocabResultStore(config=self._config)

        self._metrics = {
            "open_vocab_scans_requested": 0,
            "open_vocab_scans_completed": 0,
            "open_vocab_scans_failed": 0,
            "open_vocab_threats_found": 0,
            "open_vocab_model_unavailable": 0,
            "open_vocab_prompts_active": 0,
            "open_vocab_scan_latency_ms_avg": 0.0,
            "open_vocab_scan_queue_rejected": 0,
        }
        self._latency_samples: list[float] = []

    def _build_adapter(self) -> OpenVocabDetectorAdapter:
        provider = self._config.get("model", {}).get("provider", "grounding_dino")
        if provider == "grounding_dino":
            return GroundingDINOAdapter(config=self._config)
        return GroundingDINOAdapter(config=self._config)

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass

    def _compute_risk_score(self, detections: list[dict], prompts_meta: dict[str, dict]) -> float:
        if not detections:
            return 0.0
        scores = []
        for det in detections:
            conf = det.get("confidence", 0.0)
            label = det.get("label", "")
            meta = prompts_meta.get(label, {})
            severity = meta.get("severity", "medium")
            weight = SEVERITY_WEIGHTS.get(severity, 0.5)
            scores.append(conf * weight)
        base = min(1.0, sum(scores) / max(1, len(scores)) + 0.1 * len(scores))
        return round(base, 4)

    def _resolve_prompts(self, prompts: list[str] | None) -> list[dict]:
        if prompts:
            return [
                {
                    "text": p,
                    "threshold": self._config.get("thresholds", {}).get("default_box_threshold", 0.35),
                    "severity": "medium",
                    "prompt_id": p,
                }
                for p in prompts
            ]
        return self._prompt_library.get_enabled_prompts()

    def scan_image(
        self,
        image_path: str | None = None,
        image_array=None,
        prompts: list[str] | None = None,
        camera_id: str | None = None,
        frame_id: int | None = None,
        incident_id: str | None = None,
        source: str = "manual",
    ) -> dict:
        from backend.app.models.open_vocab_models import OpenVocabScanResult, OpenVocabDetection

        with self._lock:
            self._metrics["open_vocab_scans_requested"] += 1
            if self._active_scans >= self._max_concurrent:
                self._metrics["open_vocab_scan_queue_rejected"] += 1
                result = OpenVocabScanResult.unavailable(
                    "max concurrent scans reached",
                    camera_id=camera_id, frame_id=frame_id,
                    incident_id=incident_id, source=source,
                    prompts=prompts or [],
                )
                return result.to_dict()
            self._active_scans += 1

        t0 = time.time()
        try:
            if not self._adapter.is_available():
                with self._lock:
                    self._metrics["open_vocab_model_unavailable"] += 1
                result = OpenVocabScanResult.unavailable(
                    self._adapter.get_status().get("reason", "model unavailable"),
                    camera_id=camera_id, frame_id=frame_id,
                    incident_id=incident_id, source=source,
                    prompts=prompts or [],
                )
                self._result_store.append_result(result)
                return result.to_dict()

            prompt_metas = self._resolve_prompts(prompts)
            prompt_texts = [p["text"] for p in prompt_metas]
            prompts_by_text = {p["text"]: p for p in prompt_metas}

            image = image_path or image_array
            thresholds = {
                "box_threshold": self._config.get("thresholds", {}).get("default_box_threshold", 0.35),
                "text_threshold": self._config.get("thresholds", {}).get("default_text_threshold", 0.25),
            }

            raw_detections = self._adapter.detect(image, prompt_texts, thresholds)
            raw_detections = raw_detections[:self._max_detections]

            now = time.time()
            detections = []
            for raw in raw_detections:
                label = raw.get("label", "")
                meta = prompts_by_text.get(label, {})
                det = OpenVocabDetection(
                    label=label,
                    prompt=label,
                    confidence=raw.get("confidence", 0.0),
                    bbox=raw.get("bbox", []),
                    severity=meta.get("severity"),
                    source_model=raw.get("source_model", "unknown"),
                    frame_id=frame_id,
                    camera_id=camera_id,
                    timestamp=now,
                    metadata={},
                )
                detections.append(det)

            risk_score = self._compute_risk_score(raw_detections, prompts_by_text)

            scan_result = OpenVocabScanResult(
                scan_id=str(uuid.uuid4()),
                camera_id=camera_id,
                frame_id=frame_id,
                incident_id=incident_id,
                source=source,
                prompts=prompt_texts,
                detections=detections,
                risk_score=risk_score,
                created_at=now,
                model_id=self._adapter.get_status().get("model_id"),
                status="completed",
                error=None,
                metadata={},
            )

            self._result_store.append_result(scan_result)

            with self._lock:
                self._metrics["open_vocab_scans_completed"] += 1
                if detections:
                    self._metrics["open_vocab_threats_found"] += len(detections)
                latency_ms = (time.time() - t0) * 1000
                self._latency_samples.append(latency_ms)
                if len(self._latency_samples) > 100:
                    self._latency_samples.pop(0)
                self._metrics["open_vocab_scan_latency_ms_avg"] = (
                    sum(self._latency_samples) / len(self._latency_samples)
                )

            self._emit("OPEN_VOCAB_SCAN_COMPLETED", {
                "scan_id": scan_result.scan_id,
                "camera_id": camera_id,
                "risk_score": risk_score,
            })
            if risk_score >= self._high_risk_threshold and detections:
                self._emit("OPEN_VOCAB_THREAT_FOUND", {
                    "scan_id": scan_result.scan_id,
                    "camera_id": camera_id,
                    "risk_score": risk_score,
                    "detections": len(detections),
                })

            return scan_result.to_dict()

        except Exception as e:
            logger.exception("Open-vocab scan error: %s", e)
            with self._lock:
                self._metrics["open_vocab_scans_failed"] += 1
            self._emit("OPEN_VOCAB_SCAN_FAILED", {"camera_id": camera_id, "error": str(e)})
            from backend.app.models.open_vocab_models import OpenVocabScanResult
            result = OpenVocabScanResult.unavailable(
                str(e), camera_id=camera_id, frame_id=frame_id,
                incident_id=incident_id, source=source, prompts=prompts or [],
            )
            result.status = "error"
            self._result_store.append_result(result)
            return result.to_dict()
        finally:
            with self._lock:
                self._active_scans -= 1

    def scan_latest_frame(self, camera_id: str, prompts: list[str] | None = None) -> dict:
        # Check cooldown
        with self._lock:
            last = self._camera_last_scan.get(camera_id, 0)
            if time.time() - last < self._cooldown:
                return {"status": "cooldown", "camera_id": camera_id}
            self._camera_last_scan[camera_id] = time.time()

        # No direct frame access here — caller must pass frame data
        return {"status": "unavailable", "reason": "no_frame_source", "camera_id": camera_id}

    def scan_incident(self, incident_id: str, prompts: list[str] | None = None) -> dict:
        return {"status": "unavailable", "reason": "no_frame_source", "incident_id": incident_id}

    def scan_frame_metadata(self, snapshot_record: dict, prompts: list[str] | None = None) -> dict:
        frame_path = snapshot_record.get("frame_path") or snapshot_record.get("image_path")
        camera_id = snapshot_record.get("camera_id")
        frame_id = snapshot_record.get("frame_id")
        incident_id = snapshot_record.get("incident_id")
        if not frame_path:
            return {"status": "unavailable", "reason": "no frame path in snapshot record"}
        return self.scan_image(
            image_path=frame_path,
            camera_id=camera_id,
            frame_id=frame_id,
            incident_id=incident_id,
            source="frame_metadata",
            prompts=prompts,
        )

    def should_scan_frame(
        self,
        camera_id: str,
        risk_score: float | None = None,
        events: list | None = None,
    ) -> bool:
        if self._config.get("scan_policy", {}).get("run_on_every_frame", False):
            return True
        if self._run_on_high_risk and risk_score is not None and risk_score >= self._high_risk_threshold:
            return True
        with self._lock:
            last = self._camera_last_scan.get(camera_id, 0)
            if time.time() - last < self._cooldown:
                return False
        return False

    def get_status(self) -> dict:
        adapter_status = self._adapter.get_status()
        with self._lock:
            metrics = dict(self._metrics)
            metrics["open_vocab_prompts_active"] = len(self._prompt_library.get_enabled_prompts())
        return {
            "enabled": self._config.get("enabled", True),
            "adapter": adapter_status,
            "metrics": metrics,
            "config": {
                "max_concurrent_scans": self._max_concurrent,
                "cooldown_seconds_per_camera": self._cooldown,
                "max_detections_per_frame": self._max_detections,
            },
        }

    def get_metrics(self) -> dict:
        with self._lock:
            m = dict(self._metrics)
            m["open_vocab_prompts_active"] = len(self._prompt_library.get_enabled_prompts())
        return m

    def get_result_store(self) -> OpenVocabResultStore:
        return self._result_store

    def get_prompt_library(self) -> OpenVocabPromptLibrary:
        return self._prompt_library
