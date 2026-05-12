from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount, UserStatus
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


def _install(monkeypatch):
    users = {
        "viewer": _user("viewer"),
        "operator": _user("operator"),
        "supervisor": _user("supervisor", metadata={"camera_scopes": ["cam_gis"]}),
    }
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_gis_config_requires_gis_read(monkeypatch):
    _install(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/gis/config").status_code == 401
    r = client.get("/api/gis/config", headers={"Authorization": "Bearer viewer"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "provider" in body["item"]


def test_geofence_write_requires_gis_write(monkeypatch):
    _install(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    payload = {
        "name": "t",
        "zone_type": "restricted",
        "polygon": [
            {"latitude": 30.0, "longitude": 71.0},
            {"latitude": 30.01, "longitude": 71.0},
            {"latitude": 30.01, "longitude": 71.01},
        ],
        "severity": "high",
    }
    denied = client.post("/api/gis/geofences", json=payload, headers={"Authorization": "Bearer operator"})
    assert denied.status_code == 403
    ok = client.post("/api/gis/geofences", json=payload, headers={"Authorization": "Bearer supervisor"})
    assert ok.status_code == 200
    assert ok.json()["item"]["zone_id"].startswith("zone_")


def test_camera_put_requires_scope(monkeypatch, tmp_path):
    import app.repositories.gis_repository as gr

    monkeypatch.setattr(gr, "_camera_profiles_path", lambda: tmp_path / "c.jsonl")
    monkeypatch.setattr(gr, "_geofences_path", lambda: tmp_path / "g.jsonl")
    gr.reset_gis_repository_singleton()
    _install(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)
    body = {
        "camera_id": "cam_gis",
        "name": "Gate",
        "latitude": 30.1,
        "longitude": 71.1,
        "heading_degrees": 0,
        "fov_degrees": 60,
        "coverage_radius_meters": 50,
    }
    r = client.put("/api/gis/cameras/cam_gis", json=body, headers={"Authorization": "Bearer supervisor"})
    assert r.status_code == 200
    gr.reset_gis_repository_singleton()
