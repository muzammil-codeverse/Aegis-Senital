"""Tests for DroneMissionExecutionService (Phase 45).

All tests use a mocked simulator client — no live simulator required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.drone_mission_models import (
    DroneMissionCreateRequest,
    DroneMissionSession,
    DroneMissionStatus,
    DroneWaypoint,
)
from app.repositories.drone_mission_repository import DroneMissionRepository
from app.services.drone.drone_mission_execution_service import (
    DroneMissionExecutionService,
    MissionExecutionError,
)
from app.services.drone.drone_mission_service import DroneMissionService


@pytest.fixture
def repo(tmp_path):
    return DroneMissionRepository(root_dir=tmp_path)


@pytest.fixture
def plan_svc(repo):
    return DroneMissionService(repository=repo)


@pytest.fixture
def exec_svc(repo):
    return DroneMissionExecutionService(repository=repo)


def _wps(n=2):
    return [
        DroneWaypoint(latitude=30.1575 + i * 0.001, longitude=71.5249, altitude_meters=40, velocity_mps=5)
        for i in range(n)
    ]


def _create_mission_and_session(plan_svc, repo, n=2):
    req = DroneMissionCreateRequest(name="Exec test patrol", waypoints=_wps(n))
    mission = plan_svc.create_mission(req, created_by="test")
    session = DroneMissionSession(
        mission_id=mission.mission_id,
        drone_id=mission.assigned_drone_id,
        total_waypoints=len(mission.waypoints),
    )
    repo.start_session(session)
    return mission, session


class TestStartMission:
    def test_fails_gracefully_when_simulator_disconnected(self, plan_svc, exec_svc, repo):
        """When simulator is not connected, mission transitions to 'failed' without raising."""
        mission, session = _create_mission_and_session(plan_svc, repo)
        # No simulator → _get_airsim_client returns None
        result = exec_svc.start_mission(mission, session)
        assert result.status == DroneMissionStatus.FAILED
        assert result.last_error is not None
        # Verify a SIMULATOR_DISCONNECTED event was recorded
        events = repo.list_events(session_id=session.session_id)
        types = [e.event_type.value for e in events]
        assert "simulator_disconnected" in types

    def test_starts_when_simulator_connected(self, plan_svc, exec_svc, repo):
        """When simulator is connected, mission transitions to 'executing'."""
        mission, session = _create_mission_and_session(plan_svc, repo)
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        with patch.object(exec_svc, "_get_airsim_client", return_value=mock_client):
            result = exec_svc.start_mission(mission, session)
        assert result.status == DroneMissionStatus.EXECUTING
        events = repo.list_events(session_id=session.session_id)
        assert any(e.event_type.value == "mission_started" for e in events)


class TestPauseMission:
    def test_pause_executing_session(self, plan_svc, exec_svc, repo):
        mission, session = _create_mission_and_session(plan_svc, repo)
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        with patch.object(exec_svc, "_get_airsim_client", return_value=mock_client):
            exec_svc.start_mission(mission, session)
        updated = exec_svc.pause_mission(session.session_id)
        assert updated.status == DroneMissionStatus.PAUSED

    def test_pause_non_executing_raises(self, plan_svc, exec_svc, repo):
        _, session = _create_mission_and_session(plan_svc, repo)
        # Session is DRAFT — not executing
        with pytest.raises(MissionExecutionError):
            exec_svc.pause_mission(session.session_id)


class TestCancelMission:
    def test_cancel_session(self, plan_svc, exec_svc, repo):
        mission, session = _create_mission_and_session(plan_svc, repo)
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        with patch.object(exec_svc, "_get_airsim_client", return_value=mock_client):
            exec_svc.start_mission(mission, session)
        updated = exec_svc.cancel_mission(session.session_id)
        assert updated.status == DroneMissionStatus.CANCELLED


class TestGetMissionStatus:
    def test_not_found(self, exec_svc):
        status = exec_svc.get_mission_status("nonexistent")
        assert status["status"] == "not_found"

    def test_found(self, plan_svc, exec_svc, repo):
        _, session = _create_mission_and_session(plan_svc, repo)
        status = exec_svc.get_mission_status(session.session_id)
        assert status["session_id"] == session.session_id
        assert status["simulated"] is True
        assert status["operator_review_required"] is True
