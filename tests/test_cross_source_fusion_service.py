"""Tests for Phase 46 CrossSourceFusionService."""
import sys
from datetime import datetime, timezone
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


class _MockUser:
    username = "test"
    role = "admin"
    user_id = "u1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _make_obs(source_type, source_id, lat=30.1575, lon=71.5249, event_type="weapon_detected",
              simulated=False, with_ref=True, evidence=None):
    from app.models.drone_fusion_models import FusionObservation, FusionSourceRef
    return FusionObservation(
        source_type=source_type,
        source_id=source_id,
        event_id=f"evt_{source_id}",
        timestamp=_now(),
        latitude=lat,
        longitude=lon,
        geo_missing=(lat is None),
        event_type=event_type,
        simulated=simulated,
        evidence_refs=evidence or [f"evt_{source_id}"],
        source_ref=FusionSourceRef(
            source_type=source_type,
            source_id=source_id,
            simulated=simulated,
        ) if with_ref else None,
    )


def _make_repo(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    return DroneFusionRepository(root_dir=tmp_path / "fusion")


def test_correlate_fixed_and_drone(tmp_path):
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    repo = _make_repo(tmp_path)
    svc = CrossSourceFusionService(repo)

    obs_fixed = _make_obs("fixed_camera", "cam_01")
    obs_drone = _make_obs("drone_simulation", "drone_01", lat=30.1576, lon=71.5250, simulated=True)

    correlations = svc.correlate([obs_fixed, obs_drone], user=_MockUser())
    assert len(correlations) >= 1
    c = correlations[0]
    assert c.confidence >= 0.35
    assert c.operator_review_required is True
    assert c.review_status == "pending"


def test_no_source_ref_no_correlation(tmp_path):
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    repo = _make_repo(tmp_path)
    svc = CrossSourceFusionService(repo)

    obs_a = _make_obs("fixed_camera", "cam_01", with_ref=False, evidence=[])
    obs_b = _make_obs("drone_simulation", "drone_01", with_ref=False, evidence=[])

    correlations = svc.correlate([obs_a, obs_b], user=_MockUser())
    assert correlations == []


def test_low_confidence_suppressed(tmp_path):
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    repo = _make_repo(tmp_path)
    svc = CrossSourceFusionService(repo)

    # Far apart (> 120m) and very different timestamps
    obs_a = _make_obs("fixed_camera", "cam_far", lat=30.0, lon=71.0)
    obs_b = _make_obs("drone_simulation", "drone_far", lat=31.0, lon=72.0, simulated=True)

    correlations = svc.correlate([obs_a, obs_b], user=_MockUser())
    for c in correlations:
        assert c.confidence >= 0.35, "All returned correlations must meet min threshold"


def test_safe_wording_in_correlation(tmp_path):
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    from app.models.drone_fusion_models import FORBIDDEN_PHRASES
    repo = _make_repo(tmp_path)
    svc = CrossSourceFusionService(repo)

    obs_a = _make_obs("fixed_camera", "cam_01")
    obs_b = _make_obs("drone_simulation", "drone_01", simulated=True)

    correlations = svc.correlate([obs_a, obs_b], user=_MockUser())
    for c in correlations:
        lower = c.safe_summary.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lower, f"Forbidden phrase '{phrase}' found in safe_summary"


def test_time_score_deterministic():
    from app.services.drone_fusion.fusion_service import _compute_time_score
    s1 = _compute_time_score("2026-01-01T00:00:00Z", "2026-01-01T00:00:10Z", 20)
    s2 = _compute_time_score("2026-01-01T00:00:00Z", "2026-01-01T00:00:10Z", 20)
    assert s1 == s2
    assert 0.0 <= s1 <= 1.0
    assert s1 > 0.0  # 10s < 20s max


def test_geo_score_deterministic():
    from app.services.drone_fusion.fusion_service import _compute_geo_score
    obs_a = _make_obs("fixed_camera", "c", lat=30.1575, lon=71.5249)
    obs_b = _make_obs("drone_simulation", "d", lat=30.1576, lon=71.5250, simulated=True)
    s1 = _compute_geo_score(obs_a, obs_b, 120)
    s2 = _compute_geo_score(obs_a, obs_b, 120)
    assert s1 == s2
    assert 0.0 <= s1 <= 1.0


def test_geo_score_missing_geo():
    from app.services.drone_fusion.fusion_service import _compute_geo_score
    from app.models.drone_fusion_models import FusionObservation, FusionSourceRef
    obs_a = FusionObservation(source_type="fixed_camera", source_id="x", geo_missing=True,
                               source_ref=FusionSourceRef(source_type="fixed_camera", source_id="x"))
    obs_b = FusionObservation(source_type="drone_simulation", source_id="y", geo_missing=False,
                               latitude=30.0, longitude=71.0,
                               source_ref=FusionSourceRef(source_type="drone_simulation", source_id="y"))
    score = _compute_geo_score(obs_a, obs_b, 120)
    assert score == 0.0, "geo_missing observation should score 0"


def test_invalid_source_pair_not_correlated(tmp_path):
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    repo = _make_repo(tmp_path)
    svc = CrossSourceFusionService(repo)

    obs_a = _make_obs("drone_simulation", "d1", simulated=True)
    obs_b = _make_obs("drone_simulation", "d2", simulated=True)

    correlations = svc.correlate([obs_a, obs_b], user=_MockUser())
    assert correlations == [], "drone_sim ↔ drone_sim is not a valid source pair"
