from __future__ import annotations

from app.services.runtime_health_service import RuntimeHealthService


def test_production_readiness_fails_when_liveness_enabled_without_provider(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    def _fake_identity_config():
        return {
            "enabled": True,
            "face": {"enabled": False},
            "reid": {"enabled": False},
            "liveness": {"enabled": True, "provider": "none", "fail_if_enabled_without_provider": True},
            "calibration": {"enabled": False},
        }

    monkeypatch.setattr("inference.identity.runtime_config.load_identity_config", _fake_identity_config)
    svc = RuntimeHealthService(config={})
    ready = svc.is_ready()
    failures = ready.get("failures") or []
    assert any("liveness enabled but provider unavailable" in f for f in failures)
