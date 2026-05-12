from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount, UserStatus
from app.services import auth_service as auth_module
from main import app


def _user(role: str = "viewer") -> UserAccount:
    return UserAccount(
        user_id="u",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


def test_gis_config_contract(monkeypatch):
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda token: _user("viewer"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/gis/config", headers={"Authorization": "Bearer viewer"})
    assert r.status_code == 200
    item = r.json()["item"]
    assert set(item.keys()) >= {"enabled", "provider", "map", "cameras", "events", "heatmap", "geofencing", "frontend"}
