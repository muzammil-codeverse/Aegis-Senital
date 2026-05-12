from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services import auth_service as auth_module
from app.models.security_models import UserAccount
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
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_model_governance_registry_requires_auth(client):
    r = client.get("/api/model-governance/registry")
    assert r.status_code == 401


def test_model_governance_validate_supervisor(client, monkeypatch):
    _install_auth(monkeypatch)
    r = client.post("/api/model-governance/validate", headers={"Authorization": "Bearer supervisor"})
    assert r.status_code == 200
    assert "status" in r.json()


def test_model_governance_registry_supervisor(client, monkeypatch):
    _install_auth(monkeypatch)
    r = client.get("/api/model-governance/registry", headers={"Authorization": "Bearer supervisor"})
    assert r.status_code == 200
    assert "entries" in r.json()
