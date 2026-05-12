"""Tests for Phase 46 fusion ↔ investigation integration."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_investigation_models_include_fusion_step_types():
    from app.models.investigation_models import HypothesisStepType
    import typing
    args = typing.get_args(HypothesisStepType)
    assert "fusion_correlation_step" in args
    assert "cross_source_observation" in args
    assert "drone_camera_handoff" in args


def test_fusion_timeline_builds_from_repo(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.models.drone_fusion_models import FusionObservation, FusionSourceRef

    repo = DroneFusionRepository(root_dir=tmp_path / "inv_test")
    obs = FusionObservation(
        source_type="fixed_camera", source_id="cam_01", case_id="case_001",
        event_id="evt_001", timestamp="2026-01-01T00:00:00+00:00",
        source_ref=FusionSourceRef(source_type="fixed_camera", source_id="cam_01"),
    )
    repo.save_observation(obs)

    timeline = repo.build_fusion_timeline(case_id="case_001")
    assert len(timeline.entries) >= 1
    assert timeline.entries[0].entry_type == "observation"


def test_accepted_correlation_persisted(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.models.drone_fusion_models import (
        CrossSourceCorrelation, FusionConfidenceBreakdown, FusionReviewRequest
    )

    repo = DroneFusionRepository(root_dir=tmp_path / "path_test")
    corr = CrossSourceCorrelation(
        primary_observation_id="obs_a",
        matched_observation_id="obs_b",
        source_pair=["fixed_camera", "drone_simulation"],
        confidence=0.72,
        confidence_breakdown=FusionConfidenceBreakdown(weighted_total=0.72),
        evidence_refs=["e1"],
    )
    repo.save_correlation(corr)
    review = FusionReviewRequest(action="accept", notes="looks good")
    updated = repo.review_correlation(corr.correlation_id, review, "operator")
    assert updated.review_status == "accepted"

    listed = repo.list_correlations(review_status="accepted")
    assert any(c.correlation_id == corr.correlation_id for c in listed)
