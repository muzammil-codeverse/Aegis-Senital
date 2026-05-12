"""Tests for Phase 46 fusion authorization behavior."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_unauthorized_camera_observation_hidden(monkeypatch):
    import app.services.drone_fusion.observation_normalizer as norm_mod
    monkeypatch.setattr(norm_mod, "can_access_camera", lambda cam_id, user: False)

    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event

    class _User:
        username = "restricted"
        role = "viewer"
        user_id = "u2"

    event = {"camera_id": "secret_cam", "event_id": "x", "timestamp": "2026-01-01T00:00:00Z"}
    obs = normalize_fixed_camera_event(event, object(), _User())
    assert obs is None, "Unauthorized camera observation must be hidden"


def test_simulated_flag_preserved_for_drone():
    from app.services.drone_fusion.observation_normalizer import normalize_drone_simulation_event

    class _User:
        username = "u"
        role = "admin"
        user_id = "u1"

    event = {"source_id": "drone_01", "timestamp": "2026-01-01T00:00:00Z", "latitude": 30.0, "longitude": 71.0}
    obs = normalize_drone_simulation_event(event, _User())
    assert obs.simulated is True, "Drone simulation observations must always be simulated=True"


def test_correlation_requires_source_refs(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    from app.services.drone_fusion.fusion_service import CrossSourceFusionService
    from app.models.drone_fusion_models import FusionObservation

    class _User:
        username = "u"
        role = "admin"
        user_id = "u1"

    repo = DroneFusionRepository(root_dir=tmp_path / "auth_test")
    svc = CrossSourceFusionService(repo)

    obs_a = FusionObservation(source_type="fixed_camera", source_id="x", source_ref=None, evidence_refs=[])
    obs_b = FusionObservation(source_type="drone_simulation", source_id="y", source_ref=None, evidence_refs=[])

    results = svc.correlate([obs_a, obs_b], user=_User())
    assert results == [], "No source_ref + no evidence_refs must yield no correlations"
