"""Tests for drone patrol mission Pydantic models (Phase 45)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.drone_mission_models import (
    DroneMissionCreateRequest,
    DroneMissionEvent,
    DroneMissionEventType,
    DroneMissionPlan,
    DroneMissionReport,
    DroneMissionSession,
    DroneMissionStatus,
    DroneMissionTelemetryPoint,
    DroneWaypoint,
)


def _wp(**kwargs):
    base = dict(latitude=30.1575, longitude=71.5249, altitude_meters=40.0, velocity_mps=5.0)
    base.update(kwargs)
    return DroneWaypoint(**base)


class TestDroneWaypoint:
    def test_valid(self):
        wp = _wp()
        assert wp.latitude == 30.1575
        assert wp.altitude_meters == 40.0

    def test_invalid_latitude(self):
        with pytest.raises(ValidationError):
            _wp(latitude=91.0)

    def test_invalid_longitude(self):
        with pytest.raises(ValidationError):
            _wp(longitude=181.0)

    def test_altitude_must_be_positive(self):
        with pytest.raises(ValidationError):
            _wp(altitude_meters=0.0)

    def test_velocity_must_be_positive(self):
        with pytest.raises(ValidationError):
            _wp(velocity_mps=0.0)


class TestDroneMissionPlan:
    def test_defaults(self):
        m = DroneMissionPlan(mission_id="m1", waypoints=[_wp()])
        assert m.simulated is True
        assert m.operator_review_required is True
        assert m.status == DroneMissionStatus.DRAFT

    def test_safe_label_present(self):
        m = DroneMissionPlan(mission_id="m1", waypoints=[])
        assert "operator review" in m.safe_label.lower()

    def test_no_forbidden_wording(self):
        m = DroneMissionPlan(mission_id="m1", waypoints=[])
        for field in (m.name, m.safe_label, m.description or ""):
            for forbidden in ("target confirmed", "suspect confirmed", "real drone deployed"):
                assert forbidden.lower() not in field.lower()


class TestDroneMissionSession:
    def test_defaults(self):
        s = DroneMissionSession(mission_id="m1")
        assert s.simulated is True
        assert s.operator_review_required is True


class TestDroneMissionEvent:
    def test_safe_label(self):
        evt = DroneMissionEvent(
            session_id="s1",
            mission_id="m1",
            event_type=DroneMissionEventType.WAYPOINT_REACHED,
        )
        assert evt.simulated is True
        assert "simulated" in evt.safe_label.lower()


class TestDroneMissionReport:
    def test_summary_safe_wording(self):
        r = DroneMissionReport(session_id="s1", mission_id="m1")
        assert r.simulated is True
        assert r.operator_review_required is True
        assert "simulated" in r.summary.lower()


class TestDroneMissionCreateRequest:
    def test_valid_request(self):
        req = DroneMissionCreateRequest(
            name="Test patrol",
            waypoints=[_wp(), _wp(latitude=30.16)],
        )
        assert len(req.waypoints) == 2
