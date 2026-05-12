from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.models.gis_models import CameraGeoProfile
from app.models.security_models import UserAccount, UserStatus
from app.services.camera_graph_service import (
    _haversine_meters,
    _transition_score,
    build_camera_graph,
    estimate_travel_seconds,
    get_edges_from,
)


def _make_user(role: str = "analyst") -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def _make_profile(cam_id: str, lat: float, lon: float) -> CameraGeoProfile:
    return CameraGeoProfile(camera_id=cam_id, name=cam_id, latitude=lat, longitude=lon)


def test_haversine_deterministic():
    d1 = _haversine_meters(30.0, 71.0, 30.001, 71.001)
    d2 = _haversine_meters(30.0, 71.0, 30.001, 71.001)
    assert d1 == d2
    assert d1 > 0


def test_haversine_zero_same_point():
    assert _haversine_meters(30.0, 71.0, 30.0, 71.0) == 0.0


def test_transition_score_closer_is_higher():
    s_close = _transition_score(50, 500, False)
    s_far = _transition_score(400, 500, False)
    assert s_close > s_far


def test_fov_overlap_bonus():
    s_no_overlap = _transition_score(100, 500, False)
    s_overlap = _transition_score(100, 500, True)
    assert s_overlap > s_no_overlap


def test_transition_score_capped_at_1():
    score = _transition_score(0, 500, True)
    assert score <= 1.0


def test_build_camera_graph_excludes_unauthorized():
    user = _make_user("operator")
    user.camera_ids = ["cam_01"]

    repo = MagicMock()
    repo.list_camera_geo_profiles.return_value = [
        _make_profile("cam_01", 30.15, 71.52),
    ]

    nodes, edges = build_camera_graph(repo, user)
    assert len(nodes) == 1
    camera_ids = {n.camera_id for n in nodes}
    assert "cam_01" in camera_ids


def test_build_camera_graph_edges_bidirectional():
    user = _make_user("admin")
    repo = MagicMock()
    repo.list_camera_geo_profiles.return_value = [
        _make_profile("cam_01", 30.150, 71.520),
        _make_profile("cam_02", 30.151, 71.521),
    ]
    nodes, edges = build_camera_graph(repo, user)
    camera_ids = {n.camera_id for n in nodes}
    assert {"cam_01", "cam_02"}.issubset(camera_ids)
    froms = {e.from_camera_id for e in edges}
    tos = {e.to_camera_id for e in edges}
    assert "cam_01" in froms
    assert "cam_02" in froms


def test_build_camera_graph_no_edges_far_cameras():
    user = _make_user("admin")
    repo = MagicMock()
    repo.list_camera_geo_profiles.return_value = [
        _make_profile("cam_01", 30.0, 71.0),
        _make_profile("cam_02", 35.0, 75.0),
    ]
    nodes, edges = build_camera_graph(repo, user)
    assert edges == []


def test_get_edges_from():
    user = _make_user("admin")
    repo = MagicMock()
    repo.list_camera_geo_profiles.return_value = [
        _make_profile("cam_01", 30.150, 71.520),
        _make_profile("cam_02", 30.151, 71.521),
        _make_profile("cam_03", 30.152, 71.522),
    ]
    _, edges = build_camera_graph(repo, user)
    from_01 = get_edges_from(edges, "cam_01")
    assert all(e.from_camera_id == "cam_01" for e in from_01)


def test_estimate_travel_seconds_modes():
    from app.models.investigation_models import CameraGraphEdge
    edge = CameraGraphEdge(
        from_camera_id="a",
        to_camera_id="b",
        distance_meters=140,
        estimated_walk_seconds=100,
        estimated_run_seconds=40,
        estimated_vehicle_seconds=18,
    )
    assert estimate_travel_seconds(edge, "walk") == 100
    assert estimate_travel_seconds(edge, "run") == 40
    assert estimate_travel_seconds(edge, "vehicle") == 18
