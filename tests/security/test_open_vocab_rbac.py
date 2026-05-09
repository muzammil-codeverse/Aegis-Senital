"""Lightweight RBAC tests for open-vocab endpoints. No model inference."""
from __future__ import annotations

from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from fastapi.testclient import TestClient
from main import app


def _user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "analyst": _user("analyst"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_viewer_can_get_open_vocab_status(monkeypatch):
    """Viewer role has open_vocab:read permission — status endpoint must return 200."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/status", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_viewer_can_get_open_vocab_prompts(monkeypatch):
    """Viewer can read prompt library."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/prompts", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_viewer_can_get_open_vocab_results(monkeypatch):
    """Viewer can read scan results."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/results", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_operator_cannot_create_prompt(monkeypatch):
    """Operator does not have open_vocab:write — prompt creation must return 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/open-vocab/prompts",
        headers={"Authorization": "Bearer operator"},
        json={"text": "test threat", "category": "other", "severity": "medium"},
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"


def test_analyst_can_trigger_scan(monkeypatch):
    """Analyst has open_vocab:write — scan endpoint must return 200 or 503 (not 403)."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/open-vocab/scan/latest-frame/cam-test",
        headers={"Authorization": "Bearer analyst"},
        json={},
    )
    assert response.status_code in {200, 503}, (
        f"Expected 200 or 503 (not 403), got {response.status_code}"
    )


def test_invalid_token_returns_401(monkeypatch):
    """An unrecognised Bearer token must yield 401."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/status", headers={"Authorization": "Bearer unknown-token"})
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"


def test_no_token_returns_401():
    """Missing authorization header must yield 401."""
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/status")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"


def test_supervisor_can_create_prompt(monkeypatch):
    """Supervisor has open_vocab:write — should get 200 or 503, not 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/open-vocab/prompts",
        headers={"Authorization": "Bearer supervisor"},
        json={"text": "test person", "category": "suspicious_behavior", "severity": "medium"},
    )
    # 200 OK, or 400 validation, or 503 unavailable — but never 403
    assert response.status_code != 403, f"Supervisor should not receive 403, got {response.status_code}"
