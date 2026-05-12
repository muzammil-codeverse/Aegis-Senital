"""Tests for drone mission REST endpoints (Phase 45)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

import app.api.drone_mission_routes as mission_routes
from app.models.security_models import UserAccount, UserStatus
from app.services import auth_service as auth_module
from main import app


def _admin_user():
    return UserAccount(
        user_id="u-admin",
        username="admin",
        display_name="Admin",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


SAMPLE_MISSION = {
    "name": "Test Simulated Patrol",
    "route_type": "linear",
    "waypoints": [
        {"latitude": 30.1575, "longitude": 71.5249, "altitude_meters": 40, "velocity_mps": 5},
        {"latitude": 30.1585, "longitude": 71.5260, "altitude_meters": 45, "velocity_mps": 5},
    ],
}


@pytest.fixture
def client_with_admin(monkeypatch):
    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _admin_user())
    return TestClient(app, raise_server_exceptions=False)


class TestListMissions:
    def test_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        res = client.get("/api/drone-missions")
        assert res.status_code in (401, 403)

    def test_returns_list(self, client_with_admin):
        res = client_with_admin.get("/api/drone-missions", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "count" in data


class TestCreateMission:
    def test_creates_mission(self, client_with_admin):
        res = client_with_admin.post("/api/drone-missions", json=SAMPLE_MISSION, headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200
        data = res.json()
        assert data["item"]["simulated"] is True
        assert data["item"]["operator_review_required"] is True

    def test_requires_min_waypoints(self, client_with_admin):
        bad = dict(SAMPLE_MISSION, waypoints=[SAMPLE_MISSION["waypoints"][0]])
        res = client_with_admin.post("/api/drone-missions", json=bad, headers={"Authorization": "Bearer admin"})
        assert res.status_code in (400, 422)

    def test_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/api/drone-missions", json=SAMPLE_MISSION)
        assert res.status_code in (401, 403)


class TestGetMission:
    def test_not_found(self, client_with_admin):
        res = client_with_admin.get("/api/drone-missions/nonexistent", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 404

    def test_found(self, client_with_admin):
        r = client_with_admin.post("/api/drone-missions", json=SAMPLE_MISSION, headers={"Authorization": "Bearer admin"})
        mid = r.json()["item"]["mission_id"]
        res = client_with_admin.get(f"/api/drone-missions/{mid}", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200


class TestStartMission:
    def test_start_mission(self, client_with_admin):
        r = client_with_admin.post("/api/drone-missions", json=SAMPLE_MISSION, headers={"Authorization": "Bearer admin"})
        mid = r.json()["item"]["mission_id"]
        payload = {"mission_id": mid}
        res = client_with_admin.post(f"/api/drone-missions/{mid}/start", json=payload, headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200
        data = res.json()
        # Status is either executing or failed (simulator may not be running)
        assert data["item"]["status"] in ("executing", "failed")
        assert data["item"]["simulated"] is True


class TestSessionEndpoints:
    @pytest.fixture
    def session_id(self, client_with_admin):
        r = client_with_admin.post("/api/drone-missions", json=SAMPLE_MISSION, headers={"Authorization": "Bearer admin"})
        mid = r.json()["item"]["mission_id"]
        r2 = client_with_admin.post(f"/api/drone-missions/{mid}/start", json={"mission_id": mid}, headers={"Authorization": "Bearer admin"})
        return r2.json()["item"]["session_id"]

    def test_status(self, client_with_admin, session_id):
        res = client_with_admin.get(f"/api/drone-missions/sessions/{session_id}/status", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200

    def test_telemetry(self, client_with_admin, session_id):
        res = client_with_admin.get(f"/api/drone-missions/sessions/{session_id}/telemetry", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200

    def test_events(self, client_with_admin, session_id):
        res = client_with_admin.get(f"/api/drone-missions/sessions/{session_id}/events", headers={"Authorization": "Bearer admin"})
        assert res.status_code == 200

    def test_cancel(self, client_with_admin, session_id):
        res = client_with_admin.post(f"/api/drone-missions/sessions/{session_id}/cancel", headers={"Authorization": "Bearer admin"})
        assert res.status_code in (200, 409)
