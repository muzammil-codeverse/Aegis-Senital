from __future__ import annotations

from app.core import persistence as persistence_module


def test_development_allows_jsonl(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    persistence_module.reset_persistence_config_cache()
    assert persistence_module.get_store_backend("cases") == "jsonl"
    assert persistence_module.get_store_backend("audit_logs") == "jsonl"


def test_production_prefers_postgres_for_required_stores(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    persistence_module.reset_persistence_config_cache()
    assert persistence_module.get_store_backend("cases") == "postgres"
    assert persistence_module.get_store_backend("identity_registry") == "postgres"
    assert persistence_module.store_required_in_production("cases") is True


def test_backup_and_restore_controls_are_enabled():
    assert persistence_module.backup_settings().get("enabled") is True
    assert persistence_module.restore_settings().get("require_confirmation") is True
