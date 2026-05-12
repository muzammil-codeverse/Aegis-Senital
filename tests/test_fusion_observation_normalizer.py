"""Tests for Phase 46 observation normalizer."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


class _MockGisRepo:
    def get_camera_geo_profile(self, camera_id):
        if camera_id == "cam_with_geo":
            class _Profile:
                latitude = 30.1575
                longitude = 71.5249
            return _Profile()
        return None


class _MockUser:
    username = "test"
    role = "admin"
    user_id = "u1"
    accessible_camera_ids = None


def _can_access_cam(cam_id, user):
    return cam_id != "forbidden_cam"


def test_normalize_fixed_camera_event_basic(monkeypatch):
    import app.services.drone_fusion.observation_normalizer as norm_mod
    monkeypatch.setattr(norm_mod, "can_access_camera", _can_access_cam)

    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event
    event = {
        "camera_id": "cam_with_geo",
        "event_id": "evt_001",
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": "weapon_detected",
        "severity": "high",
    }
    obs = normalize_fixed_camera_event(event, _MockGisRepo(), _MockUser(), evidence_refs=["evt_001"])
    assert obs is not None
    assert obs.source_type == "fixed_camera"
    assert obs.source_ref is not None
    assert obs.simulated is False


def test_normalize_fixed_camera_event_missing_camera_id(monkeypatch):
    import app.services.drone_fusion.observation_normalizer as norm_mod
    monkeypatch.setattr(norm_mod, "can_access_camera", _can_access_cam)

    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event
    obs = normalize_fixed_camera_event({}, _MockGisRepo(), _MockUser())
    assert obs is None


def test_normalize_fixed_camera_event_unauthorized(monkeypatch):
    import app.services.drone_fusion.observation_normalizer as norm_mod
    monkeypatch.setattr(norm_mod, "can_access_camera", _can_access_cam)

    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event
    event = {"camera_id": "forbidden_cam", "event_id": "x", "timestamp": "2026-01-01T00:00:00Z"}
    obs = normalize_fixed_camera_event(event, _MockGisRepo(), _MockUser())
    assert obs is None


def test_normalize_fixed_camera_event_no_geo(monkeypatch):
    import app.services.drone_fusion.observation_normalizer as norm_mod
    monkeypatch.setattr(norm_mod, "can_access_camera", _can_access_cam)

    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event
    event = {"camera_id": "cam_no_geo", "event_id": "x", "timestamp": "2026-01-01T00:00:00Z"}
    obs = normalize_fixed_camera_event(event, _MockGisRepo(), _MockUser())
    assert obs is not None
    assert obs.geo_missing is True
    assert obs.latitude is None


def test_normalize_drone_simulation_event():
    from app.services.drone_fusion.observation_normalizer import normalize_drone_simulation_event
    event = {
        "source_id": "drone_sim_01",
        "event_id": "evt_drone_001",
        "timestamp": "2026-01-01T00:00:00Z",
        "latitude": 30.1575,
        "longitude": 71.5249,
        "altitude_meters": 50.0,
        "event_type": "weapon_detected",
    }
    obs = normalize_drone_simulation_event(event, _MockUser(), evidence_refs=["evt_drone_001"])
    assert obs is not None
    assert obs.source_type == "drone_simulation"
    assert obs.simulated is True
    assert obs.geo_missing is False
    assert obs.source_ref is not None


def test_normalize_drone_simulation_event_no_geo():
    from app.services.drone_fusion.observation_normalizer import normalize_drone_simulation_event
    event = {"source_id": "drone_01", "timestamp": "2026-01-01T00:00:00Z"}
    obs = normalize_drone_simulation_event(event, _MockUser())
    assert obs is not None
    assert obs.geo_missing is True


def test_normalize_uploaded_video_event():
    from app.services.drone_fusion.observation_normalizer import normalize_uploaded_video_event
    event = {
        "upload_id": "upload_01",
        "event_id": "evt_vid_001",
        "timestamp": "2026-01-01T00:00:00Z",
        "event_type": "weapon_detected",
    }
    obs = normalize_uploaded_video_event(event, _MockUser())
    assert obs is not None
    assert obs.source_type == "uploaded_video"
    assert obs.simulated is False
