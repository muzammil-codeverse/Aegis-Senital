from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.security_models import UserAccount, UserStatus
from app.repositories import gis_repository as gr
from app.services import auth_service as auth_module
from main import app


def _user(role: str, metadata: dict | None = None) -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata=metadata or {},
    )


@pytest.fixture
def tmp_gis(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(gr, "_camera_profiles_path", lambda: tmp_path / "c.jsonl")
    monkeypatch.setattr(gr, "_geofences_path", lambda: tmp_path / "g.jsonl")
    gr.reset_gis_repository_singleton()
    yield tmp_path
    gr.reset_gis_repository_singleton()


def test_unauthorized_camera_hidden_from_list(tmp_gis, monkeypatch):
    from app.models.gis_models import CameraGeoProfile

    gr.get_gis_repository().upsert_camera_geo_profile(
        CameraGeoProfile(
            camera_id="secret_cam",
            name="s",
            latitude=1.0,
            longitude=1.0,
        )
    )
    users = {"analyst": _user("analyst", metadata={"camera_scopes": ["other"]})}
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda token: users.get(token))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/gis/cameras", headers={"Authorization": "Bearer analyst"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_camera_detail_403_without_scope(tmp_gis, monkeypatch):
    from app.models.gis_models import CameraGeoProfile

    gr.get_gis_repository().upsert_camera_geo_profile(
        CameraGeoProfile(camera_id="cam_x", name="x", latitude=2.0, longitude=2.0)
    )
    users = {"analyst": _user("analyst", metadata={"camera_scopes": ["other"]})}
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda token: users.get(token))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/gis/cameras/cam_x", headers={"Authorization": "Bearer analyst"})
    assert r.status_code == 403
