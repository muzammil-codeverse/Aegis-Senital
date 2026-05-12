"""Tests verifying the frontend API contract for drone missions (Phase 45)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

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


@pytest.fixture
def client(monkeypatch):
    auth = auth_module.get_auth_service()
    monkeypatch.setattr(auth, "get_current_user_from_token", lambda token: _admin_user())
    return TestClient(app, raise_server_exceptions=False)


SAMPLE = {
    "name": "Frontend contract test patrol",
    "waypoints": [
        {"latitude": 30.1575, "longitude": 71.5249, "altitude_meters": 40, "velocity_mps": 5},
        {"latitude": 30.1585, "longitude": 71.5260, "altitude_meters": 45, "velocity_mps": 5},
    ],
}

HDR = {"Authorization": "Bearer admin"}


class TestAPIContract:
    """Verify response shapes match what the frontend expects."""

    def test_list_missions_shape(self, client):
        res = client.get("/api/drone-missions", headers=HDR)
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "count" in data
        assert "status" in data

    def test_create_mission_shape(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        assert res.status_code == 200
        item = res.json()["item"]
        assert "mission_id" in item
        assert "name" in item
        assert item["simulated"] is True
        assert item["operator_review_required"] is True
        assert "waypoints" in item
        assert "status" in item
        assert "estimated_distance_meters" in item

    def test_get_mission_shape(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        mid = res.json()["item"]["mission_id"]
        res2 = client.get(f"/api/drone-missions/{mid}", headers=HDR)
        assert res2.status_code == 200
        item = res2.json()["item"]
        assert "mission_id" in item
        assert "waypoints" in item

    def test_start_mission_returns_session(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        mid = res.json()["item"]["mission_id"]
        res2 = client.post(f"/api/drone-missions/{mid}/start", json={"mission_id": mid}, headers=HDR)
        assert res2.status_code == 200
        item = res2.json()["item"]
        assert "session_id" in item
        assert "status" in item
        assert item["simulated"] is True

    def test_session_status_shape(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        mid = res.json()["item"]["mission_id"]
        res2 = client.post(f"/api/drone-missions/{mid}/start", json={"mission_id": mid}, headers=HDR)
        sid = res2.json()["item"]["session_id"]
        res3 = client.get(f"/api/drone-missions/sessions/{sid}/status", headers=HDR)
        assert res3.status_code == 200
        item = res3.json()["item"]
        assert "session_id" in item
        assert "status" in item
        assert "progress_percent" in item
        assert item["simulated"] is True
        assert item["operator_review_required"] is True

    def test_telemetry_shape(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        mid = res.json()["item"]["mission_id"]
        res2 = client.post(f"/api/drone-missions/{mid}/start", json={"mission_id": mid}, headers=HDR)
        sid = res2.json()["item"]["session_id"]
        res3 = client.get(f"/api/drone-missions/sessions/{sid}/telemetry", headers=HDR)
        assert res3.status_code == 200
        data = res3.json()
        assert "items" in data
        assert "count" in data

    def test_events_shape(self, client):
        res = client.post("/api/drone-missions", json=SAMPLE, headers=HDR)
        mid = res.json()["item"]["mission_id"]
        res2 = client.post(f"/api/drone-missions/{mid}/start", json={"mission_id": mid}, headers=HDR)
        sid = res2.json()["item"]["session_id"]
        res3 = client.get(f"/api/drone-missions/sessions/{sid}/events", headers=HDR)
        assert res3.status_code == 200
        data = res3.json()
        assert "items" in data
        # At least simulator_disconnected or mission_started event recorded
        assert len(data["items"]) > 0
