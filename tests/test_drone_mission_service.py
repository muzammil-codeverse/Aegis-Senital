"""Tests for DroneMissionService (Phase 45)."""
from __future__ import annotations

import pytest

from app.models.drone_mission_models import (
    DroneMissionCreateRequest,
    DroneMissionStatus,
    DroneWaypoint,
)
from app.repositories.drone_mission_repository import DroneMissionRepository
from app.services.drone.drone_mission_service import DroneMissionService, ValidationError


@pytest.fixture
def svc(tmp_path):
    return DroneMissionService(repository=DroneMissionRepository(root_dir=tmp_path))


def _wps(n=3):
    return [
        DroneWaypoint(latitude=30.1575 + i * 0.001, longitude=71.5249, altitude_meters=40, velocity_mps=5)
        for i in range(n)
    ]


class TestValidation:
    def test_too_few_waypoints(self, svc):
        with pytest.raises(ValidationError, match="at least"):
            svc.validate_mission_plan(_wps(1))

    def test_too_many_waypoints(self, svc):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            svc.validate_mission_plan(_wps(51))

    def test_valid(self, svc):
        svc.validate_mission_plan(_wps(3))  # should not raise


class TestEstimation:
    def test_distance_positive(self, svc):
        result = svc.estimate_route(_wps(3))
        assert result["distance_meters"] > 0

    def test_duration_positive(self, svc):
        result = svc.estimate_route(_wps(3))
        assert result["duration_seconds"] > 0

    def test_single_segment(self, svc):
        wps = [
            DroneWaypoint(latitude=30.0, longitude=71.0, altitude_meters=40, velocity_mps=10),
            DroneWaypoint(latitude=30.01, longitude=71.0, altitude_meters=40, velocity_mps=10),
        ]
        result = svc.estimate_route(wps)
        assert 900 < result["distance_meters"] < 1300  # ~1111 m


class TestCreateMission:
    def test_creates_mission(self, svc):
        req = DroneMissionCreateRequest(name="Test patrol", waypoints=_wps(3))
        mission = svc.create_mission(req, created_by="tester")
        assert mission.simulated is True
        assert mission.operator_review_required is True
        assert mission.status == DroneMissionStatus.DRAFT
        assert mission.estimated_distance_meters is not None

    def test_too_few_raises(self, svc):
        req = DroneMissionCreateRequest(name="Bad patrol", waypoints=_wps(1))
        with pytest.raises(ValidationError):
            svc.create_mission(req)


class TestListAndGet:
    def test_round_trip(self, svc):
        req = DroneMissionCreateRequest(name="Round trip", waypoints=_wps(2))
        m = svc.create_mission(req)
        fetched = svc.get_mission(m.mission_id)
        assert fetched is not None
        assert fetched.mission_id == m.mission_id

    def test_list_returns_mission(self, svc):
        req = DroneMissionCreateRequest(name="Listed", waypoints=_wps(2))
        svc.create_mission(req)
        all_missions = svc.list_missions()
        assert len(all_missions) >= 1


class TestRoutePreview:
    def test_preview(self, svc):
        req = DroneMissionCreateRequest(name="Preview patrol", waypoints=_wps(3))
        m = svc.create_mission(req)
        preview = svc.generate_route_preview(m.mission_id)
        assert preview is not None
        assert len(preview.waypoints) == 3
        assert preview.simulated is True
