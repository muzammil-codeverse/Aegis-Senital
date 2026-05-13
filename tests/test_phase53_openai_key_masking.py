"""
Phase 53 — OpenAI Key Masking Tests

Verifies that the OpenAI API key is never exposed in API responses,
logs, or status outputs. The key must remain server-side only.
"""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount, UserStatus
from app.services import auth_service as auth_module
from main import app


def _user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


def test_llm_status_does_not_expose_api_key(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-TESTKEY1234567890")

    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _user("viewer"))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/llm/status", headers={"Authorization": "Bearer viewer"})
    assert resp.status_code == 200
    body = resp.text
    assert "sk-proj-TESTKEY1234567890" not in body, "OPENAI_API_KEY must not appear in /api/llm/status response"
    assert "sk-proj" not in body, "No API key prefix must appear in /api/llm/status response"


def test_health_endpoint_does_not_expose_api_key(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-TESTKEY1234567890")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.text
    assert "sk-proj-TESTKEY1234567890" not in body


def test_openai_key_present_flag_is_boolean_not_value(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-SECRETVALUE9999")

    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _user("viewer"))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/llm/status", headers={"Authorization": "Bearer viewer"})
    assert resp.status_code == 200
    data = resp.json()
    item = data.get("item", {})
    key_present = item.get("openai_key_present")
    assert isinstance(key_present, bool), "openai_key_present must be a boolean, not the key value"
    assert "sk-proj-SECRETVALUE9999" not in str(data)


def test_openai_reasoning_parameter_excluded_for_gpt_models():
    from app.services.llm_provider import OpenAIResponsesProvider

    provider = OpenAIResponsesProvider()
    for model in ("gpt-4o", "gpt-4o-mini", "gpt-5.4-mini", "gpt-5.4", "gpt-5.5"):
        assert not provider._model_supports_reasoning(model), (
            f"{model} must not be treated as a reasoning model"
        )
    for model in ("o1", "o1-mini", "o3", "o3-mini", "o4-mini"):
        assert provider._model_supports_reasoning(model), (
            f"{model} must be treated as a reasoning model"
        )
