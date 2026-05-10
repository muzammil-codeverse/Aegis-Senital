import pytest
from unittest.mock import MagicMock
from inference.anomaly.anomaly_service import AnomalyService
from inference.anomaly.pretrained_adapter import RuleOnlyAdapter, PretrainedVideoAdapter
from inference.anomaly.violence_adapter import ViolenceVisualAdapter


def test_rule_only_adapter_health():
    adapter = RuleOnlyAdapter()
    adapter.load()
    health = adapter.health()
    assert health["loaded"] is True
    assert health["provider"] == "rule_only"
    assert health["status"] == "healthy"


def test_pretrained_adapter_missing_weights():
    adapter = PretrainedVideoAdapter(model_path="models/anomaly/does_not_exist.pt")
    adapter.load()
    assert adapter.is_loaded() is False
    health = adapter.health()
    assert health["status"] == "unavailable"


def test_violence_adapter_missing_weights():
    adapter = ViolenceVisualAdapter(model_path="models/anomaly/no_violence_model.pt")
    adapter.load()
    assert adapter.is_loaded() is False
    health = adapter.health()
    assert health["status"] == "unavailable"


def test_service_health_all_fields():
    svc = AnomalyService()
    health = svc.health()
    required = ["enabled", "rule_engine_loaded", "model_loaded", "violence_adapter_loaded",
                "provider", "status", "last_error"]
    for key in required:
        assert key in health, f"Missing key: {key}"


def test_service_health_disabled():
    svc = AnomalyService()
    svc._enabled = False
    svc._status = "disabled"
    health = svc.health()
    assert health["enabled"] is False


def test_service_health_degraded_after_error():
    svc = AnomalyService()
    svc._rule_engine.evaluate = MagicMock(side_effect=Exception("boom"))
    svc._fail_open = True
    from inference.anomaly.schemas import AnomalyWindow
    svc._evaluate_window(AnomalyWindow(camera_id="cam1"))
    health = svc.health()
    assert health["status"] == "degraded"
    assert health["last_error"] is not None


def test_violence_adapter_production_fail_fast():
    adapter = ViolenceVisualAdapter(
        model_path="models/anomaly/no_model.pt",
        is_production=True,
    )
    with pytest.raises(RuntimeError, match="required in production"):
        adapter.load()


def test_violence_adapter_dev_degraded_warning():
    adapter = ViolenceVisualAdapter(
        model_path="models/anomaly/no_model.pt",
        is_production=False,
    )
    adapter.load()  # should not raise
    assert adapter.is_loaded() is False
    assert adapter.health()["status"] == "unavailable"
