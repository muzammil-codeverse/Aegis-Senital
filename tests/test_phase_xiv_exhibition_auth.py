from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount, UserStatus
from app.services import auth_service as auth_module
from main import app


def _admin_user() -> UserAccount:
    return UserAccount(
        user_id="u-admin",
        username="admin",
        display_name="System Administrator",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def _client_as_admin(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth_module.get_auth_service(), "get_current_user_from_token", lambda _token: _admin_user())
    return TestClient(app, raise_server_exceptions=False)


def test_admin_can_access_exhibition_critical_routes(monkeypatch):
    client = _client_as_admin(monkeypatch)
    headers = {"Authorization": "Bearer admin"}
    routes = [
        "/api/system/readiness",
        "/api/system/health",
        "/api/capabilities/summary",
        "/api/preflight/latest",
        "/api/exhibition-demo/status",
        "/api/visual-scenario/status",
        "/api/simulation/sources/dashboard-feeds",
        "/api/simulation/sources/cameras",
        "/api/simulation/sources/drones",
        "/api/alerts",
        "/api/incidents",
        "/api/uploaded-videos",
        "/api/map/state",
        "/api/gis/config",
        "/api/analytics/overview",
        "/api/drone-unified/fleet",
    ]

    results = {route: client.get(route, headers=headers).status_code for route in routes}

    assert all(status == 200 for status in results.values()), results


def test_simulation_dashboard_feeds_return_16_cameras_with_geometry(monkeypatch):
    client = _client_as_admin(monkeypatch)

    response = client.get("/api/simulation/sources/dashboard-feeds", headers={"Authorization": "Bearer admin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 16
    first = payload["items"][0]
    assert first["camera_id"].startswith("CAM-")
    assert "location" in first
    assert "orientation" in first
    assert "coverage" in first


def test_visual_snapshot_missing_camera_returns_clean_404(monkeypatch):
    client = _client_as_admin(monkeypatch)

    response = client.get(
        "/api/visual-scenario/snapshots/CAM-DOES-NOT-EXIST",
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 404
    assert response.json()["status"] == "error"


def test_auth_me_works_for_admin_token(monkeypatch):
    client = _client_as_admin(monkeypatch)

    response = client.get("/api/auth/me", headers={"Authorization": "Bearer admin"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "admin"
    assert payload["user"]["role"] == "admin"


def test_admin_has_map_and_gis_permissions(monkeypatch):
    client = _client_as_admin(monkeypatch)
    headers = {"Authorization": "Bearer admin"}

    assert client.get("/api/map/state", headers=headers).status_code == 200
    assert client.get("/api/gis/config", headers=headers).status_code == 200
