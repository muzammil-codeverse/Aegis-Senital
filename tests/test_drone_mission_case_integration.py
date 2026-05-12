"""Tests for drone mission case/evidence integration (Phase 45)."""
from __future__ import annotations

import pytest


class TestCaseEvidenceTypes:
    def test_drone_mission_evidence_types_registered(self):
        from app.services.case_service import _EVIDENCE_TYPE_BY_EVENT
        assert "drone_mission_report" in _EVIDENCE_TYPE_BY_EVENT
        assert "drone_mission_telemetry_manifest" in _EVIDENCE_TYPE_BY_EVENT
        assert "drone_mission_event" in _EVIDENCE_TYPE_BY_EVENT

    def test_drone_mission_report_type(self):
        from app.services.case_service import _EVIDENCE_TYPE_BY_EVENT
        assert _EVIDENCE_TYPE_BY_EVENT["drone_mission_report"] == "drone_mission_report"

    def test_simulated_flag_in_mission_report(self):
        from app.models.drone_mission_models import DroneMissionReport
        r = DroneMissionReport(session_id="s1", mission_id="m1")
        assert r.simulated is True
        assert r.operator_review_required is True

    def test_no_forbidden_wording_in_report_summary(self):
        from app.models.drone_mission_models import DroneMissionReport
        r = DroneMissionReport(session_id="s1", mission_id="m1")
        forbidden = ("target confirmed", "suspect confirmed", "real drone deployed")
        for phrase in forbidden:
            assert phrase not in r.summary.lower()
