from __future__ import annotations

import threading
import time


class _FakeAdapter:
    def __init__(self, *, sleep_seconds: float = 0.0, fail: bool = False) -> None:
        self.sleep_seconds = sleep_seconds
        self.fail = fail
        self.loaded = False
        self.load_calls = 0

    def load(self) -> None:
        self.load_calls += 1
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        if self.fail:
            raise RuntimeError("simulated load failure")
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def is_available(self) -> bool:
        return self.loaded

    def get_status(self) -> dict:
        return {
            "available": self.loaded,
            "provider": "fake",
            "model_id": "fake-open-vocab",
            "device": "cpu" if self.loaded else None,
            "reason": None if self.loaded else ("simulated load failure" if self.fail else "not loaded"),
        }


class _FakeStreamManager:
    def __init__(self) -> None:
        self.added: list[tuple[str, str | None]] = []

    def add_stream(self, source: str, stream_id: str | None = None) -> str:
        self.added.append((source, stream_id))
        return stream_id or "stream_0"

    def remove_stream(self, stream_id: str) -> bool:
        return True


def _make_scanner(auto_load: bool, require: bool, timeout: float = 0.2):
    from inference.open_vocab.scanner import OpenVocabThreatScanner

    scanner = OpenVocabThreatScanner(
        config={
            "enabled": True,
            "open_vocab_runtime": {
                "auto_load_on_camera_start": auto_load,
                "require_open_vocab_for_stream": require,
                "load_timeout_seconds": timeout,
                "unload_when_no_active_streams": False,
                "max_concurrent_scans": 1,
            },
        }
    )
    return scanner


def _reset_auto_load_metrics() -> None:
    from inference.monitoring.metrics import get_metrics as get_monitoring_metrics
    from inference.metrics import metrics as system_metrics

    for target in (get_monitoring_metrics(), system_metrics):
        for key in (
            "open_vocab_model_auto_load_attempts_total",
            "open_vocab_model_auto_load_failures_total",
            "open_vocab_model_auto_load_success_total",
            "open_vocab_model_auto_load_skipped_total",
            "open_vocab_model_auto_load_timeout_total",
        ):
            setattr(target, key, 0)


def test_auto_load_disabled_does_not_load_model():
    scanner = _make_scanner(auto_load=False, require=False)
    adapter = _FakeAdapter()
    scanner._adapter = adapter

    result = scanner.ensure_model_loaded_for_camera_start("cam-01", wait_for_result=False)

    assert result["status"] == "disabled"
    assert adapter.load_calls == 0


def test_auto_load_true_triggers_load_once():
    scanner = _make_scanner(auto_load=True, require=True)
    adapter = _FakeAdapter()
    scanner._adapter = adapter

    result = scanner.ensure_model_loaded_for_camera_start("cam-01", wait_for_result=True)

    assert result["status"] == "success"
    assert result["loaded"] is True
    assert adapter.load_calls == 1


def test_concurrent_camera_starts_deduplicate_load():
    scanner = _make_scanner(auto_load=True, require=True, timeout=1.0)
    adapter = _FakeAdapter(sleep_seconds=0.05)
    scanner._adapter = adapter
    results: list[dict] = []

    def _runner(camera_id: str) -> None:
        results.append(scanner.ensure_model_loaded_for_camera_start(camera_id, wait_for_result=True))

    threads = [threading.Thread(target=_runner, args=(f"cam-{idx}",)) for idx in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2.0)

    assert adapter.load_calls == 1
    assert len(results) == 3
    assert all(result["status"] == "success" for result in results)


def test_failed_load_does_not_stop_stream_when_require_false(monkeypatch):
    from backend.app.services.stream_session_manager import StreamSessionManager

    fake_stream_manager = _FakeStreamManager()
    manager = StreamSessionManager()
    called: list[str] = []

    monkeypatch.setattr(manager, "_get_camera_source", lambda camera_id: f"rtsp://{camera_id}")
    monkeypatch.setattr(
        manager,
        "_prepare_open_vocab_for_stream",
        lambda camera_id: called.append(camera_id) or {
            "status": "failed",
            "loaded": False,
            "error": "simulated load failure",
            "block_stream": False,
        },
    )
    monkeypatch.setattr("inference.stream.stream_manager.get_stream_manager", lambda: fake_stream_manager)

    result = manager.start_stream("cam-01")

    assert called == ["cam-01"]
    assert result["state"] == "running"
    assert result["stream_id"] == "cam_cam-01"


def test_failed_load_stops_stream_when_require_true(monkeypatch):
    from backend.app.services.stream_session_manager import StreamSessionManager

    fake_stream_manager = _FakeStreamManager()
    manager = StreamSessionManager()

    monkeypatch.setattr(manager, "_get_camera_source", lambda camera_id: f"rtsp://{camera_id}")
    monkeypatch.setattr(
        manager,
        "_prepare_open_vocab_for_stream",
        lambda camera_id: {
            "status": "failed",
            "loaded": False,
            "error": "simulated required failure",
            "block_stream": True,
        },
    )
    monkeypatch.setattr("inference.stream.stream_manager.get_stream_manager", lambda: fake_stream_manager)

    result = manager.start_stream("cam-01")

    assert result["state"] == "error"
    assert "simulated required failure" in (result.get("error_reason") or "")


def test_load_timeout_is_handled():
    scanner = _make_scanner(auto_load=True, require=True, timeout=0.05)
    adapter = _FakeAdapter(sleep_seconds=0.2)
    scanner._adapter = adapter

    result = scanner.ensure_model_loaded_for_camera_start("cam-01", wait_for_result=True, timeout_seconds=0.05)

    assert result["status"] == "timeout"
    assert result["loaded"] is False
    assert adapter.load_calls == 1


def test_auto_load_metrics_increment_correctly():
    from inference.monitoring.metrics import get_metrics as get_monitoring_metrics
    from inference.metrics import metrics as system_metrics

    _reset_auto_load_metrics()
    scanner = _make_scanner(auto_load=True, require=True)
    adapter = _FakeAdapter()
    scanner._adapter = adapter

    first = scanner.ensure_model_loaded_for_camera_start("cam-01", wait_for_result=True)
    second = scanner.ensure_model_loaded_for_camera_start("cam-02", wait_for_result=False)

    assert first["status"] == "success"
    assert second["status"] == "skipped"
    assert get_monitoring_metrics().open_vocab_model_auto_load_attempts_total == 1
    assert get_monitoring_metrics().open_vocab_model_auto_load_success_total == 1
    assert get_monitoring_metrics().open_vocab_model_auto_load_skipped_total == 1
    assert system_metrics.open_vocab_model_auto_load_attempts_total == 1
    assert system_metrics.open_vocab_model_auto_load_success_total == 1
    assert system_metrics.open_vocab_model_auto_load_skipped_total == 1


def test_health_reports_last_auto_load_status(monkeypatch):
    from backend.app.services.runtime_health_service import RuntimeHealthService

    class _FakeRuntime:
        def get_open_vocab_status(self) -> dict:
            return {
                "model_loaded": False,
                "auto_load_on_camera_start": True,
                "last_auto_load_status": "failed",
                "last_auto_load_error": "simulated load failure",
            }

    monkeypatch.setattr("inference.runtime.get_intelligence_runtime", lambda: _FakeRuntime())

    service = RuntimeHealthService(config={"services": {"open_vocab": {"required": False}}})
    health = service.get_health(include_sensitive=True)
    open_vocab = health["checks"]["open_vocab"]

    assert open_vocab["status"] == "degraded"
    assert open_vocab["auto_load_on_camera_start"] is True
    assert open_vocab["last_auto_load_status"] == "failed"
    assert open_vocab["last_auto_load_error"] == "simulated load failure"
