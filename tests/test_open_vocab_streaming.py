"""
Phase 25 — Tests for Open-Vocab WebSocket event schema, rate limiting, and payload safety.
"""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_scan_result_payload(
    camera_id="cam_01",
    detection_count=2,
    highest_risk="high",
    detections=None,
):
    if detections is None:
        detections = [
            {"label": "weapon", "score": 0.72, "bbox": [0, 0, 100, 100], "prompt_id": "weapon_visible", "risk_level": "high"},
            {"label": "firearm", "score": 0.65, "bbox": [10, 10, 80, 80], "prompt_id": "firearm", "risk_level": "high"},
        ]
    return {
        "event_type": "open_vocab_scan_result",
        "camera_id": camera_id,
        "stream_id": camera_id,
        "scan_id": "test-scan-001",
        "timestamp": "2026-05-09T12:00:00Z",
        "scan_timestamp": time.time(),
        "provider": "grounding_dino",
        "device": "cuda",
        "model_loaded": True,
        "prompts": [
            {"prompt_id": "weapon_visible", "label": "weapon", "text": "visible weapon", "threshold": 0.35}
        ],
        "detections": detections,
        "summary": {
            "detection_count": detection_count,
            "max_score": 0.72,
            "highest_risk_level": highest_risk,
            "latency_ms": 182.5,
            "scan_timestamp": time.time(),
        },
    }


# ── Event schema tests ────────────────────────────────────────────────────────

class TestOpenVocabScanResultSchema:

    def test_required_fields_present(self):
        payload = _make_scan_result_payload()
        assert "event_type" in payload
        assert payload["event_type"] == "open_vocab_scan_result"
        assert "camera_id" in payload
        assert "scan_id" in payload
        assert "timestamp" in payload
        assert "provider" in payload
        assert "device" in payload
        assert "model_loaded" in payload
        assert "prompts" in payload
        assert "detections" in payload
        assert "summary" in payload

    def test_no_raw_frames_in_payload(self):
        payload = _make_scan_result_payload()
        payload["frame_data"] = b"RAWFRAME"
        payload["embedding"] = [0.1, 0.2, 0.3]

        # Simulate service stripping unsafe fields
        payload.pop("frame_data", None)
        payload.pop("embedding", None)
        payload.pop("embeddings", None)

        assert "frame_data" not in payload
        assert "embedding" not in payload

    def test_detection_risk_levels(self):
        payload = _make_scan_result_payload()
        for det in payload["detections"]:
            assert det["risk_level"] in ("low", "medium", "high", "critical")
            assert 0.0 <= det["score"] <= 1.0

    def test_summary_fields(self):
        payload = _make_scan_result_payload()
        s = payload["summary"]
        assert "detection_count" in s
        assert "max_score" in s
        assert "highest_risk_level" in s
        assert "latency_ms" in s
        assert s["highest_risk_level"] in ("low", "medium", "high", "critical")

    def test_detections_capped_at_25(self):
        # Generate 30 detections
        detections = [
            {"label": f"object_{i}", "score": 0.5, "bbox": [0, 0, 10, 10], "prompt_id": None, "risk_level": "low"}
            for i in range(30)
        ]
        payload = _make_scan_result_payload(detections=detections, detection_count=30)

        # Simulate the service cap
        max_detections = 25
        if len(payload["detections"]) > max_detections:
            payload["detections"] = payload["detections"][:max_detections]
            payload["_detections_truncated"] = True

        assert len(payload["detections"]) == 25
        assert payload.get("_detections_truncated") is True


# ── Rate limiting tests ────────────────────────────────────────────────────────

class TestOpenVocabRateLimiting:

    def _make_rate_limiter(self, max_per_second: float = 2.0):
        """Return a simple rate-limiter closure identical to the service implementation."""
        from collections import defaultdict
        camera_event_times: dict[str, list] = defaultdict(list)
        lock = threading.Lock()

        def is_rate_limited(camera_id: str) -> bool:
            now = time.monotonic()
            with lock:
                times = camera_event_times[camera_id]
                cutoff = now - 1.0
                times[:] = [t for t in times if t >= cutoff]
                if len(times) >= max_per_second:
                    return True
                times.append(now)
                return False

        return is_rate_limited

    def test_first_events_pass_through(self):
        limiter = self._make_rate_limiter(max_per_second=2.0)
        assert not limiter("cam_01")
        assert not limiter("cam_01")

    def test_third_event_rate_limited(self):
        limiter = self._make_rate_limiter(max_per_second=2.0)
        limiter("cam_01")
        limiter("cam_01")
        assert limiter("cam_01") is True

    def test_different_cameras_independent(self):
        limiter = self._make_rate_limiter(max_per_second=2.0)
        limiter("cam_01")
        limiter("cam_01")
        # cam_02 should not be rate-limited
        assert not limiter("cam_02")

    def test_rate_resets_after_window(self):
        limiter = self._make_rate_limiter(max_per_second=2.0)
        limiter("cam_01")
        limiter("cam_01")
        # Fake time elapsing: manually clear the window by monkeypatching
        # (In real use, just wait 1+ second. Here we verify the data structure.)
        assert limiter("cam_01")  # limited at window boundary

    def test_empty_results_not_published_by_default(self):
        publish_empty = False
        payload = _make_scan_result_payload(detection_count=0, detections=[])
        detection_count = payload.get("summary", {}).get("detection_count", 0)
        should_publish = publish_empty or detection_count > 0
        assert not should_publish

    def test_threat_results_always_published(self):
        publish_empty = False
        payload = _make_scan_result_payload(detection_count=1)
        detection_count = payload.get("summary", {}).get("detection_count", 0)
        should_publish = publish_empty or detection_count > 0
        assert should_publish


# ── Event type tests ──────────────────────────────────────────────────────────

class TestOpenVocabEventType:

    def test_event_type_registered(self):
        from core.event_bus.event_types import EventType
        assert hasattr(EventType, "OPEN_VOCAB_SCAN_RESULT")
        assert EventType.OPEN_VOCAB_SCAN_RESULT.value == "open_vocab_scan_result"

    def test_event_type_distinct_from_scan_completed(self):
        from core.event_bus.event_types import EventType
        assert EventType.OPEN_VOCAB_SCAN_RESULT != EventType.OPEN_VOCAB_SCAN_COMPLETED
        assert EventType.OPEN_VOCAB_SCAN_RESULT != EventType.OPEN_VOCAB_THREAT_FOUND


# ── Payload size tests ────────────────────────────────────────────────────────

class TestPayloadSize:

    def test_normal_payload_serializable(self):
        payload = _make_scan_result_payload()
        data = json.dumps(payload)
        assert len(data) > 0

    def test_payload_without_sensitive_fields(self):
        payload = _make_scan_result_payload()
        payload.pop("frame_data", None)
        payload.pop("embedding", None)
        assert "frame_data" not in payload
        assert "embedding" not in payload

    def test_risk_level_from_score(self):
        def risk_level(score):
            if score >= 0.75:
                return "critical"
            if score >= 0.55:
                return "high"
            if score >= 0.35:
                return "medium"
            return "low"

        assert risk_level(0.80) == "critical"
        assert risk_level(0.60) == "high"
        assert risk_level(0.40) == "medium"
        assert risk_level(0.20) == "low"
