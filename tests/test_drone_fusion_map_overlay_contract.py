"""Tests for Phase 46 fusion map overlay contract."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def _make_obs(source_type, source_id, lat=None, lon=None, geo_missing=False):
    from app.models.drone_fusion_models import FusionObservation, FusionSourceRef
    return FusionObservation(
        source_type=source_type,
        source_id=source_id,
        latitude=lat,
        longitude=lon,
        geo_missing=geo_missing or (lat is None),
        source_ref=FusionSourceRef(source_type=source_type, source_id=source_id),
    )


def test_map_overlay_line_requires_both_geo():
    """Correlation line must not be drawn if either observation lacks geo."""
    obs_a = _make_obs("fixed_camera", "cam_01", lat=30.15, lon=71.52)
    obs_b = _make_obs("drone_simulation", "d1", geo_missing=True)

    has_geo_a = not obs_a.geo_missing and obs_a.latitude is not None
    has_geo_b = not obs_b.geo_missing and obs_b.latitude is not None

    # Overlay line must NOT be drawn if either geo is missing
    line_renderable = has_geo_a and has_geo_b
    assert not line_renderable, "Line should not be drawn when one endpoint has no geo"


def test_map_overlay_line_both_geo():
    obs_a = _make_obs("fixed_camera", "cam_01", lat=30.15, lon=71.52)
    obs_b = _make_obs("drone_simulation", "d1", lat=30.155, lon=71.525)

    has_geo_a = not obs_a.geo_missing and obs_a.latitude is not None
    has_geo_b = not obs_b.geo_missing and obs_b.latitude is not None
    line_renderable = has_geo_a and has_geo_b
    assert line_renderable, "Line should be drawn when both endpoints have geo"


def test_fusion_timeline_safe_summary_no_forbidden():
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.models.drone_fusion_models import FORBIDDEN_PHRASES, FusionObservation, FusionSourceRef
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmp:
        repo = DroneFusionRepository(root_dir=tmp)
        obs = FusionObservation(
            source_type="fixed_camera", source_id="c", case_id="case_map",
            source_ref=FusionSourceRef(source_type="fixed_camera", source_id="c"),
        )
        repo.save_observation(obs)
        tl = repo.build_fusion_timeline(case_id="case_map")
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in tl.safe_summary.lower(), f"Forbidden phrase in timeline: {phrase}"
