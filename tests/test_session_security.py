from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from main import app


def _user(role: str = "operator") -> UserAccount:
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


def test_production_login_uses_secure_cookie_mode(monkeypatch):
    service = auth_module.get_auth_service()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        service,
        "login",
        lambda username, password, request=None: {
            "access_token": "prod-token",
            "token_type": "bearer",
            "user": _user().to_dict(),
            "permissions": ["camera:read"],
            "expires_in_seconds": 3600,
        },
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/auth/login", json={"username": "alice", "password": "pw"})

    assert response.status_code == 200
    payload = response.json()
    assert "access_token" not in payload
    assert payload["token_type"] == "cookie"
    assert payload["auth_storage_mode"] == "cookie"

    set_cookie = response.headers.get("set-cookie", "")
    assert "aegis_access_token=" in set_cookie
    assert "aegis_csrf_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie


def test_cookie_backed_writes_require_csrf(monkeypatch):
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: _user() if token == "cookie-token" else None)

    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("aegis_access_token", "cookie-token")

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "old-password", "new_password": "NewPassword123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF validation failed"


def test_frontend_token_storage_is_explicitly_gated():
    config_source = Path("frontend/src/config.js").read_text(encoding="utf-8")
    client_source = Path("frontend/src/api/client.js").read_text(encoding="utf-8")

    assert "VITE_AUTH_STORAGE_MODE" in config_source
    assert "VITE_ALLOW_DEV_TOKEN_STORAGE" in config_source
    assert "function allowClientTokenStorage" in config_source
    assert "if (!allowClientTokenStorage()) return null" in client_source
