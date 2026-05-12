from __future__ import annotations

import pytest
from app.models.investigation_models import (
    InvestigationTimeline,
    InvestigationTimelineEntry,
    PathHypothesis,
    InvestigationSubjectRef,
)


def test_investigation_timeline_structure():
    timeline = InvestigationTimeline(
        case_id="case_001",
        entries=[],
        total_hypotheses=0,
    )
    assert timeline.case_id == "case_001"
    assert isinstance(timeline.entries, list)


def test_timeline_counts_correctly():
    timeline = InvestigationTimeline(
        case_id="case_002",
        total_hypotheses=3,
        accepted=1,
        rejected=1,
        inconclusive=0,
        pending=1,
    )
    assert timeline.accepted + timeline.rejected + timeline.inconclusive + timeline.pending == timeline.total_hypotheses


def test_timeline_entry_has_operator_review():
    entry = InvestigationTimelineEntry(
        entry_id="e1",
        case_id="case_001",
        event_type="path_hypothesis",
        summary="Possible movement path requiring operator review.",
        timestamp="2026-01-01T00:00:00Z",
    )
    assert entry.operator_review_required is True


def test_repository_build_case_timeline():
    from unittest.mock import patch, MagicMock
    from app.repositories.investigation_repository import InvestigationRepository

    hyp = PathHypothesis(
        hypothesis_id="hyp_c1",
        subject_ref=InvestigationSubjectRef(type="manual", ref_id="r1"),
        case_id="case_tl",
        review_status="pending",
        safe_summary="Possible movement path.",
        evidence_refs=["event:evt_001"],
    )

    with patch.object(InvestigationRepository, "list_hypotheses", return_value=[hyp]):
        with patch.object(InvestigationRepository, "save_timeline", side_effect=lambda t: t):
            repo = InvestigationRepository.__new__(InvestigationRepository)
            timeline = repo.build_case_timeline("case_tl")

    assert timeline.case_id == "case_tl"
    assert timeline.total_hypotheses == 1
    assert timeline.pending == 1
    assert len(timeline.entries) == 1
