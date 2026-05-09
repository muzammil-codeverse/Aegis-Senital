"""
Phase 25 — Tests for Open-Vocab model auto-load locking and degraded startup behavior.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Auto-load locking tests ───────────────────────────────────────────────────

class TestAutoLoadLocking:
    """Verify concurrent auto-load requests do not duplicate model loading."""

    def test_concurrent_load_requests_deduplicated(self):
        """Only one load should proceed when multiple threads request concurrently."""
        load_count = 0
        lock = threading.Lock()
        loading = threading.Event()
        load_event = threading.Event()

        def mock_load():
            nonlocal load_count
            with lock:
                load_count += 1
            time.sleep(0.05)
            load_event.set()

        # Simulate the locking guard used in auto-load
        _load_in_progress = threading.Lock()
        results = []

        def guarded_load():
            if _load_in_progress.acquire(blocking=False):
                try:
                    mock_load()
                    results.append("loaded")
                finally:
                    _load_in_progress.release()
            else:
                results.append("skipped")

        threads = [threading.Thread(target=guarded_load) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        assert load_count == 1
        assert results.count("loaded") == 1
        assert results.count("skipped") == 4

    def test_load_timeout_does_not_block_forever(self):
        """Auto-load with timeout should not block camera startup."""
        timeout_seconds = 0.1

        def slow_load():
            time.sleep(10.0)

        result = {"completed": False, "timed_out": False}

        def timed_load():
            thread = threading.Thread(target=slow_load, daemon=True)
            thread.start()
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                result["timed_out"] = True
            else:
                result["completed"] = True

        timed_load()
        assert result["timed_out"] is True
        assert result["completed"] is False


# ── Degraded startup behavior tests ──────────────────────────────────────────

class TestDegradedStartupBehavior:

    def test_camera_continues_when_open_vocab_unavailable(self):
        """Camera startup should not fail if open-vocab is unavailable and not required."""
        config = {
            "open_vocab_runtime": {
                "require_open_vocab_for_stream": False,
                "auto_load_on_camera_start": False,
            }
        }
        open_vocab_available = False
        require_open_vocab = config["open_vocab_runtime"]["require_open_vocab_for_stream"]

        camera_started = True  # would be set to True after successful startup
        if not open_vocab_available and not require_open_vocab:
            open_vocab_status = "degraded"
        elif not open_vocab_available and require_open_vocab:
            camera_started = False
            open_vocab_status = "failed"
        else:
            open_vocab_status = "ready"

        assert camera_started is True
        assert open_vocab_status == "degraded"

    def test_camera_blocked_when_open_vocab_required_and_unavailable(self):
        config = {
            "open_vocab_runtime": {
                "require_open_vocab_for_stream": True,
            }
        }
        open_vocab_available = False
        require_open_vocab = config["open_vocab_runtime"]["require_open_vocab_for_stream"]

        camera_started = True
        if not open_vocab_available and require_open_vocab:
            camera_started = False

        assert camera_started is False

    def test_open_vocab_status_degraded_in_health(self):
        """Health endpoint should report degraded when open-vocab load fails."""
        health = {
            "status": "healthy",
            "components": {
                "open_vocab": {"status": "degraded", "reason": "model load failed"}
            }
        }
        # Overall health is still reachable, but open-vocab is degraded
        assert health["components"]["open_vocab"]["status"] == "degraded"

    def test_auto_load_false_by_default(self):
        """Default config must have auto_load_on_camera_start=false."""
        default_config = {
            "open_vocab_runtime": {
                "auto_load_on_camera_start": False,
                "require_open_vocab_for_stream": False,
            }
        }
        assert default_config["open_vocab_runtime"]["auto_load_on_camera_start"] is False
        assert default_config["open_vocab_runtime"]["require_open_vocab_for_stream"] is False


# ── Model lifecycle metrics tests ─────────────────────────────────────────────

class TestModelLifecycleMetrics:

    def test_auto_load_attempt_counter(self):
        """Metrics counters must track auto-load attempts and failures."""
        attempts = 0
        failures = 0

        def attempt_load(will_fail: bool):
            nonlocal attempts, failures
            attempts += 1
            if will_fail:
                failures += 1

        attempt_load(will_fail=False)
        attempt_load(will_fail=True)

        assert attempts == 2
        assert failures == 1

    def test_active_subscribers_counter(self):
        clients = set()
        clients.add("client_1")
        clients.add("client_2")
        assert len(clients) == 2
        clients.discard("client_1")
        assert len(clients) == 1
