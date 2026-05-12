from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.repositories import gis_repository as gr
from app.services import auth_service as auth_module
from app.models.security_models import UserAccount, UserStatus
from main import app


def _user(role: str = "supervisor") -> UserAccount:
    return UserAccount(
        user_id="u1",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


@pytest.fixture
def tmp_gis(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gr, "_camera_profiles_path", lambda: tmp_path / "c.jsonl")
    monkeypatch.setattr(gr, "_geofences_path", lambda: tmp_path / "g.jsonl")
    gr.reset_gis_repository_singleton()
    yield
    gr.reset_gis_repository_singleton()


def test_geofence_patch_and_delete(tmp_gis, monkeypatch):
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda token: _user("supervisor"))
    client = TestClient(app, raise_server_exceptions=False)
    create = client.post(
        "/api/gis/geofences",
        headers={"Authorization": "Bearer supervisor"},
        json={
            "name": "z1",
            "zone_type": "restricted",
            "polygon": [
                {"latitude": 1.0, "longitude": 1.0},
                {"latitude": 1.0, "longitude": 1.01},
                {"latitude": 1.01, "longitude": 1.01},
            ],
        },
    )
    assert create.status_code == 200
    zid = create.json()["item"]["zone_id"]
    patch = client.patch(
        f"/api/gis/geofences/{zid}",
        headers={"Authorization": "Bearer supervisor"},
        json={"name": "z1-renamed"},
    )
    assert patch.status_code == 200
    deleted = client.delete(f"/api/gis/geofences/{zid}", headers={"Authorization": "Bearer supervisor"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
