"""
Phase 53 — Production Validation Contract Tests

Verifies that the production environment priority logic, OpenAI provider
conditional reasoning, and persistence production gates behave correctly.
"""
from __future__ import annotations

import os


def test_aegis_env_takes_priority_over_app_env_in_persistence(monkeypatch):
    from app.core import persistence as pm

    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.setenv("APP_ENV", "development")
    assert pm.is_production_environment() is True

    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("APP_ENV", "production")
    assert pm.is_production_environment() is False


def test_aegis_env_takes_priority_over_app_env_in_security_config(monkeypatch):
    from app.security import config as sc

    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.setenv("APP_ENV", "development")
    assert sc.is_production_environment() is True

    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("APP_ENV", "production")
    assert sc.is_production_environment() is False


def test_aegis_env_takes_priority_over_app_env_in_llm_service(monkeypatch):
    from app.services import llm_service as ls

    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.setenv("APP_ENV", "development")
    assert ls._is_production() is True

    monkeypatch.setenv("AEGIS_ENV", "development")
    monkeypatch.setenv("APP_ENV", "production")
    assert ls._is_production() is False


def test_openai_provider_excludes_reasoning_for_gpt_models():
    from app.services.llm_provider import OpenAIResponsesProvider

    provider = OpenAIResponsesProvider()
    assert provider._model_supports_reasoning("gpt-4o") is False
    assert provider._model_supports_reasoning("gpt-5.4-mini") is False
    assert provider._model_supports_reasoning("gpt-5.5") is False
    assert provider._model_supports_reasoning("o1-mini") is True
    assert provider._model_supports_reasoning("o3") is True
    assert provider._model_supports_reasoning("o4-mini") is True


def test_production_persistence_requires_postgres_when_configured(monkeypatch):
    from app.core import persistence as pm

    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    assert pm.is_production_environment() is True
    assert pm.require_postgres() is True
    assert pm.prohibit_jsonl_fallback() is True


def test_development_persistence_allows_jsonl(monkeypatch):
    from app.core import persistence as pm

    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    pm.reset_persistence_config_cache()
    assert pm.is_production_environment() is False
    assert pm.get_store_backend("cases") == "jsonl"
    assert pm.get_store_backend("audit_logs") == "jsonl"


def test_jwt_secret_env_var_resolution(monkeypatch):
    import importlib
    from app.security import config as sc

    secret = "phase53-test-secret-string-" + "x" * 40
    monkeypatch.setenv("AEGIS_JWT_SECRET", secret)
    monkeypatch.setenv("AEGIS_ENV", "development")
    sc.load_security_config.cache_clear()
    cfg = sc.load_security_config()
    assert cfg["auth"]["_jwt_secret"] == secret
    sc.load_security_config.cache_clear()
