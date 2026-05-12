"""Tests for the DroneMissionRepository (Phase 45)."""
from __future__ import annotations

import tempfile

import pytest

from app.models.drone_mission_models import (
    DroneMissionEvent,
    DroneMissionEventType,
    DroneMissionPlan,
    DroneMissionReport,
    DroneMissionSession,
    DroneMissionStatus,
    DroneMissionTelemetryPoint,
    DroneWaypoint,
)
from app.repositories.drone_mission_repository import DroneMissionRepository


@pytest.fixture
def repo(tmp_path):
    return DroneMissionRepository(root_dir=tmp_path)


def _mission():
    return DroneMissionPlan(
        mission_id="m1",
        name="Test Patrol",
        waypoints=[
            DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=40, velocity_mps=5),
        ],
    )


def _session(mission_id="m1"):
    return DroneMissionSession(mission_id=mission_id)


class TestMissionCRUD:
    def test_create_and_get(self, repo):
        m = _mission()
        repo.create_mission(m)
        fetched = repo.get_mission(m.mission_id)
        assert fetched is not None
        assert fetched.mission_id == m.mission_id

    def test_list_missions(self, repo):
        repo.create_mission(_mission())
        items = repo.list_missions()
        assert len(items) >= 1

    def test_list_missions_status_filter(self, repo):
        repo.create_mission(_mission())
        drafts = repo.list_missions(status=DroneMissionStatus.DRAFT)
        assert all(m.status == DroneMissionStatus.DRAFT for m in drafts)

    def test_update_mission(self, repo):
        m = _mission()
        repo.create_mission(m)
        updated = repo.update_mission(m.mission_id, {"name": "Updated Patrol"})
        assert updated is not None
        assert updated.name == "Updated Patrol"

    def test_delete_mission(self, repo):
        m = _mission()
        repo.create_mission(m)
        assert repo.delete_mission(m.mission_id) is True
        assert repo.get_mission(m.mission_id) is None

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_mission("nonexistent") is None


class TestSessionCRUD:
    def test_start_and_get(self, repo):
        s = _session()
        repo.start_session(s)
        fetched = repo.get_session(s.session_id)
        assert fetched is not None

    def test_update_session(self, repo):
        s = _session()
        repo.start_session(s)
        updated = repo.update_session(s.session_id, {"progress_percent": 50.0})
        assert updated is not None
        assert updated.progress_percent == 50.0

    def test_list_sessions(self, repo):
        s = _session("m2")
        repo.start_session(s)
        results = repo.list_sessions(mission_id="m2")
        assert len(results) >= 1


class TestTelemetry:
    def test_append_and_list(self, repo):
        pt = DroneMissionTelemetryPoint(session_id="s1", mission_id="m1")
        repo.append_telemetry(pt)
        results = repo.list_telemetry("s1")
        assert len(results) == 1


class TestEvents:
    def test_append_and_list(self, repo):
        evt = DroneMissionEvent(
            session_id="s1", mission_id="m1",
            event_type=DroneMissionEventType.MISSION_STARTED,
        )
        repo.append_event(evt)
        results = repo.list_events(session_id="s1")
        assert len(results) == 1


class TestReports:
    def test_save_and_get(self, repo):
        r = DroneMissionReport(session_id="s1", mission_id="m1")
        repo.save_report(r)
        fetched = repo.get_report("s1")
        assert fetched is not None
        assert fetched.session_id == "s1"


class TestHealthCheck:
    def test_health_is_healthy(self, repo):
        health = repo.health_check()
        assert health["status"] == "healthy"
        assert "storage_backend" in health
