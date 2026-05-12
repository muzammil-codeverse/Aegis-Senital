from __future__ import annotations

import pytest
from app.models.investigation_models import (
    PathHypothesis,
    PathHypothesisStep,
    InvestigationSubjectRef,
)


def test_hypothesis_has_steps_list():
    hyp = PathHypothesis(
        hypothesis_id="hyp_001",
        subject_ref=InvestigationSubjectRef(type="manual", ref_id="r1"),
    )
    assert isinstance(hyp.steps, list)


def test_hypothesis_step_has_lat_lon():
    step = PathHypothesisStep(
        step_index=0,
        camera_id="cam_01",
        timestamp="2026-01-01T00:00:00Z",
        latitude=30.15,
        longitude=71.52,
    )
    assert step.latitude == pytest.approx(30.15)
    assert step.longitude == pytest.approx(71.52)


def test_hypothesis_step_low_confidence_flag():
    step = PathHypothesisStep(
        step_index=1,
        camera_id="cam_02",
        timestamp="2026-01-01T00:05:00Z",
        low_confidence_transition=True,
    )
    assert step.low_confidence_transition is True


def test_hypothesis_serializes_for_map():
    hyp = PathHypothesis(
        hypothesis_id="hyp_map",
        subject_ref=InvestigationSubjectRef(type="event", ref_id="evt_001"),
        steps=[
            PathHypothesisStep(step_index=0, camera_id="c1", timestamp="t1", latitude=30.0, longitude=71.0),
            PathHypothesisStep(step_index=1, camera_id="c2", timestamp="t2", latitude=30.01, longitude=71.01),
        ],
        confidence=0.72,
    )
    data = hyp.model_dump(mode="json")
    assert "steps" in data
    assert len(data["steps"]) == 2
    assert "confidence" in data
    assert "hypothesis_id" in data
    assert "safe_summary" in data


def test_hypothesis_evidence_refs_serializable():
    hyp = PathHypothesis(
        hypothesis_id="hyp_ev",
        subject_ref=InvestigationSubjectRef(type="manual", ref_id="r1"),
        evidence_refs=["event:evt_001", "case:case_001"],
    )
    data = hyp.model_dump(mode="json")
    assert isinstance(data["evidence_refs"], list)
    assert len(data["evidence_refs"]) == 2
