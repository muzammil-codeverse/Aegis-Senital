from __future__ import annotations

from app.services.gis_service import evaluate_gis_readiness
from app.services.runtime_health_service import RuntimeHealthService


def test_runtime_health_includes_gis_block():
    svc = RuntimeHealthService(config={})
    health = svc.get_health(include_sensitive=False)
    assert "gis" in health.get("checks", {})
    gis = health["checks"]["gis"]
    assert "provider" in gis
    assert "camera_profiles" in gis


def test_production_mapbox_missing_key_fails_readiness(monkeypatch):
    def fake(name: str):
        if name == "gis":
            return {
                "gis": {
                    "enabled": True,
                    "provider": {"default": "mapbox", "require_api_key_in_production": True},
                    "frontend": {"mapbox_env_var": "VITE_MAPBOX_TOKEN"},
                }
            }
        raise FileNotFoundError(name)

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("VITE_MAPBOX_TOKEN", raising=False)
    monkeypatch.setattr("app.services.gis_service.load_runtime_config", fake)
    r = evaluate_gis_readiness()
    assert r["status"] == "failed"
