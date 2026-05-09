from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
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
        "operator": _user("operator"),
        "analyst": _user("analyst"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_health_remains_public():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code != 401
    assert response.status_code != 403


def test_metrics_core_requires_metrics_read(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/metrics/core").status_code == 401
    assert client.get("/metrics/core", headers={"Authorization": "Bearer operator"}).status_code == 200


def test_identities_requires_identity_read(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/identities", headers={"Authorization": "Bearer viewer"}).status_code == 403
    assert client.get("/api/identities", headers={"Authorization": "Bearer analyst"}).status_code in {200, 503}


def test_sensitive_writes_require_admin_or_write_permissions(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/api/watchlist", headers={"Authorization": "Bearer operator"}, json={}).status_code == 403
    assert client.post("/api/models/reload", headers={"Authorization": "Bearer analyst"}).status_code == 403


def test_invalid_token_returns_401(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/metrics/core", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_insufficient_permission_returns_403(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/models/reload", headers={"Authorization": "Bearer operator"})
    assert response.status_code == 403
    assert response.json()["status"] == "error"
