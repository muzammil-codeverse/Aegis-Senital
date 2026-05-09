"""
RBAC tests for open-vocab model hot-load endpoints.
No model inference is performed — tests verify permission enforcement only.

Phase 24 — Production Deployment Foundation
"""
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


# ── Load endpoint RBAC ────────────────────────────────────────────────────────

def test_viewer_cannot_load_model(monkeypatch):
    """Viewer does not have open_vocab:write — load must return 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"


def test_analyst_can_load_model(monkeypatch):
    """Analyst has open_vocab:write per RBAC config — load must return 200 or 503, not 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer analyst"})
    assert response.status_code in {200, 503}, (
        f"Expected 200 or 503 (not 403), got {response.status_code}"
    )


def test_admin_can_load_model(monkeypatch):
    """Admin has open_vocab:write — load must return 200 or 503, not 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer admin"})
    assert response.status_code in {200, 503}, (
        f"Expected 200 or 503 (not 403), got {response.status_code}"
    )


# ── Unload endpoint RBAC ──────────────────────────────────────────────────────

def test_viewer_cannot_unload_model(monkeypatch):
    """Viewer does not have open_vocab:write — unload must return 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/unload", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"


def test_admin_can_unload_model(monkeypatch):
    """Admin has open_vocab:write — unload must return 200 or 503, not 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/unload", headers={"Authorization": "Bearer admin"})
    assert response.status_code in {200, 503}, (
        f"Expected 200 or 503 (not 403), got {response.status_code}"
    )


# ── Reload endpoint RBAC ──────────────────────────────────────────────────────

def test_admin_can_reload_model(monkeypatch):
    """Admin has open_vocab:write — reload must return 200 or 503, not 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/reload", headers={"Authorization": "Bearer admin"})
    assert response.status_code in {200, 503}, (
        f"Expected 200 or 503 (not 403), got {response.status_code}"
    )


def test_operator_cannot_reload_model(monkeypatch):
    """Operator does not have open_vocab:write — reload must return 403."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/reload", headers={"Authorization": "Bearer operator"})
    assert response.status_code == 403, f"Expected 403, got {response.status_code}"


# ── Status endpoint RBAC ──────────────────────────────────────────────────────

def test_viewer_can_get_model_status(monkeypatch):
    """Viewer has open_vocab:read — status endpoint must return 200."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/model/status", headers={"Authorization": "Bearer viewer"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


def test_analyst_can_get_model_status(monkeypatch):
    """Analyst has open_vocab:read — status endpoint must return 200."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/model/status", headers={"Authorization": "Bearer analyst"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


# ── Auth failures ─────────────────────────────────────────────────────────────

def test_invalid_token_returns_401_on_load(monkeypatch):
    """An unrecognised Bearer token must yield 401 on the load endpoint."""
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer no-such-token"})
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"


def test_no_token_returns_401_on_status():
    """Missing authorization header must yield 401 on the status endpoint."""
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/open-vocab/model/status")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
