from app.services.model_governance_service import load_model_governance_config, reset_model_governance_config_cache


def test_model_governance_config_loads():
    reset_model_governance_config_cache()
    cfg = load_model_governance_config()
    root = cfg.get("model_governance") or {}
    assert root.get("enabled") is True
    assert root.get("registry", {}).get("prohibit_dual_writes") is True
    rollback = root.get("rollback") or {}
    assert rollback.get("require_audit_reason") is True
