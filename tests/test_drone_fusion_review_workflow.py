"""Tests for Phase 46 fusion review workflow (accept/reject/inconclusive)."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def _make_correlation(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.models.drone_fusion_models import (
        CrossSourceCorrelation, FusionConfidenceBreakdown, FusionObservation, FusionSourceRef
    )
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService

    repo = DroneFusionRepository(root_dir=tmp_path / "review_test")

    class _User:
        username = "reviewer"
        role = "admin"
        user_id = "u1"

    obs_a = FusionObservation(
        source_type="fixed_camera", source_id="cam_01", timestamp="2026-01-01T00:00:00+00:00",
        latitude=30.1575, longitude=71.5249, event_type="weapon_detected", evidence_refs=["e1"],
        source_ref=FusionSourceRef(source_type="fixed_camera", source_id="cam_01"),
    )
    obs_b = FusionObservation(
        source_type="drone_simulation", source_id="d1", timestamp="2026-01-01T00:00:05+00:00",
        latitude=30.1576, longitude=71.5250, event_type="weapon_detected", simulated=True,
        evidence_refs=["e2"],
        source_ref=FusionSourceRef(source_type="drone_simulation", source_id="d1", simulated=True),
    )
    svc = CrossSourceFusionService(repo)
    correlations = svc.correlate([obs_a, obs_b], user=_User())
    return repo, correlations


def test_accept_correlation(tmp_path):
    from app.models.drone_fusion_models import FusionReviewRequest
    repo, corrs = _make_correlation(tmp_path)
    assert corrs, "Need at least one correlation"
    corr_id = corrs[0].correlation_id

    review = FusionReviewRequest(action="accept", notes="Looks plausible")
    updated = repo.review_correlation(corr_id, review, reviewed_by="reviewer")
    assert updated is not None
    assert updated.review_status == "accepted"
    assert updated.reviewed_by == "reviewer"


def test_reject_correlation(tmp_path):
    from app.models.drone_fusion_models import FusionReviewRequest
    repo, corrs = _make_correlation(tmp_path)
    assert corrs
    corr_id = corrs[0].correlation_id

    review = FusionReviewRequest(action="reject", notes="Not relevant")
    updated = repo.review_correlation(corr_id, review, reviewed_by="reviewer")
    assert updated.review_status == "rejected"


def test_inconclusive_correlation(tmp_path):
    from app.models.drone_fusion_models import FusionReviewRequest
    repo, corrs = _make_correlation(tmp_path)
    assert corrs
    corr_id = corrs[0].correlation_id

    review = FusionReviewRequest(action="inconclusive", notes="Need more data")
    updated = repo.review_correlation(corr_id, review, reviewed_by="reviewer")
    assert updated.review_status == "inconclusive"


def test_review_nonexistent_correlation(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.models.drone_fusion_models import FusionReviewRequest
    repo = DroneFusionRepository(root_dir=tmp_path / "missing")
    review = FusionReviewRequest(action="accept")
    result = repo.review_correlation("nonexistent_id", review, reviewed_by="user")
    assert result is None
