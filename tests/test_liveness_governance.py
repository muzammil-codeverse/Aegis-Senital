from app.services.model_governance_service import load_model_governance_config, reset_model_governance_config_cache


def test_liveness_provider_marked_in_governance_yaml():
    reset_model_governance_config_cache()
    cfg = load_model_governance_config().get("model_governance") or {}
    live = cfg.get("liveness_provider") or {}
    assert live.get("status") == "disabled"
    assert live.get("roadmap_required") is True
