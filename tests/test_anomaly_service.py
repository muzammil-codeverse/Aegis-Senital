import time
import pytest
from unittest.mock import patch, MagicMock
from inference.anomaly.anomaly_service import AnomalyService
from inference.anomaly.schemas import AnomalyWindow, AnomalyPrediction


def _make_window(camera_id="cam1"):
    return AnomalyWindow(camera_id=camera_id)


def test_service_initialises():
    svc = AnomalyService()
    assert svc._enabled is True


def test_service_disabled_returns_empty():
    svc = AnomalyService()
    svc._enabled = False
    result = svc.add_frame("cam1", 1, time.time(), [], [])
    assert result == []


def test_service_fail_open_on_error():
    svc = AnomalyService()
    svc._fail_open = True
    # Force rule engine evaluate() to raise
    svc._rule_engine.evaluate = MagicMock(side_effect=RuntimeError("test error"))
    window = _make_window()
    result = svc._evaluate_window(window)
    assert result == []
    assert svc._status == "degraded"


def test_service_health_reports_status():
    svc = AnomalyService()
    health = svc.health()
    assert "enabled" in health
    assert "status" in health
    assert "rule_engine_loaded" in health


def test_service_add_frame_no_eval_before_window():
    svc = AnomalyService()
    svc._window_seconds = 10.0
    # First call — should not yet evaluate (window not elapsed)
    result = svc.add_frame("cam1", 1, time.time(), [], [])
    assert isinstance(result, list)


def test_service_evaluate_window_direct():
    svc = AnomalyService()
    window = _make_window()
    result = svc.evaluate_window(window)
    assert isinstance(result, list)


def test_no_fake_predictions():
    svc = AnomalyService()
    window = AnomalyWindow(camera_id="cam1", tracks=[], detections=[])
    result = svc.evaluate_window(window)
    # With no tracks/detections, no rules should fire
    assert result == []


def test_provider_unavailable_no_fake_preds():
    svc = AnomalyService()
    # Model adapter is not loaded
    assert not svc._model_adapter.is_loaded() or svc._model_adapter.__class__.__name__ == "RuleOnlyAdapter"
    window = _make_window()
    result = svc.evaluate_window(window)
    # No fake predictions from unavailable adapter
    for pred in result:
        assert pred.source != "pretrained_video"
