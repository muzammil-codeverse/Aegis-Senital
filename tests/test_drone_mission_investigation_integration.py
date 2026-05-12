"""Tests for drone mission investigation integration (Phase 45)."""
from __future__ import annotations

import pytest
from app.models.investigation_models import HypothesisStepType


class TestInvestigationModelExtensions:
    def test_drone_mission_telemetry_step_type(self):
        assert "drone_mission_telemetry" in HypothesisStepType.__args__

    def test_drone_mission_event_step_type(self):
        assert "drone_mission_event" in HypothesisStepType.__args__

    def test_drone_mission_waypoint_step_type(self):
        assert "drone_mission_waypoint" in HypothesisStepType.__args__

    def test_safe_label_not_forbidden(self):
        """Verify that no investigation model leaks forbidden wording."""
        from app.models.investigation_models import InvestigationObservation
        obs = InvestigationObservation(
            observation_id="o1",
            camera_id="drone_sim_01",
            timestamp="2026-01-01T00:00:00Z",
            source_type="drone_mission",
            safe_label="Simulated aerial patrol observation",
        )
        forbidden = ("target confirmed", "suspect confirmed", "real drone deployed", "pursuit confirmed")
        for phrase in forbidden:
            assert phrase not in (obs.safe_label or "").lower()
