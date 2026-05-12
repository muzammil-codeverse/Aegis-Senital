from __future__ import annotations

from pathlib import Path

import pytest

from app.models.gis_models import CameraGeoProfile, GeoFenceZone, GeoPoint
from app.models.security_models import UserAccount, UserStatus
from app.repositories import gis_repository as gr
from app.services import gis_service as gs
from app.services.gis_service import (
    compute_camera_fov_polygon,
    compute_risk_heatmap,
    distance_meters,
    find_nearby_cameras,
    point_in_geofence,
    validate_coordinates,
)


def _user(role: str = "supervisor", **meta) -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata=dict(meta),
    )


@pytest.fixture
def isolated_repo(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(gr, "_camera_profiles_path", lambda: tmp_path / "cam.jsonl")
    monkeypatch.setattr(gr, "_geofences_path", lambda: tmp_path / "geo.jsonl")
    gr.reset_gis_repository_singleton()
    repo = gr.get_gis_repository()
    yield repo
    gr.reset_gis_repository_singleton()


def test_validate_coordinates():
    validate_coordinates(0, 0)
    with pytest.raises(ValueError):
        validate_coordinates(100, 0)


def test_fov_polygon_deterministic(isolated_repo):
    p = CameraGeoProfile(
        camera_id="c1",
        name="n",
        latitude=30.1575,
        longitude=71.5249,
        heading_degrees=90.0,
        fov_degrees=60.0,
        coverage_radius_meters=100.0,
    )
    a = compute_camera_fov_polygon(p)
    b = compute_camera_fov_polygon(p)
    assert [pt.model_dump() for pt in a] == [pt.model_dump() for pt in b]
    assert len(a) >= 4


def test_distance_meters():
    p1 = GeoPoint(latitude=30.0, longitude=71.0)
    p2 = GeoPoint(latitude=30.001, longitude=71.0)
    d = distance_meters(p1, p2)
    assert 100 < d < 200


def test_nearby_cameras_ordering(isolated_repo):
    isolated_repo.upsert_camera_geo_profile(
        CameraGeoProfile(camera_id="near_a", name="a", latitude=30.0, longitude=71.0)
    )
    isolated_repo.upsert_camera_geo_profile(
        CameraGeoProfile(camera_id="near_b", name="b", latitude=30.002, longitude=71.0)
    )
    u = _user("supervisor")
    res = find_nearby_cameras(isolated_repo, u, 30.0, 71.0, radius_meters=5000)
    assert res[0].distance_meters <= res[1].distance_meters


def test_point_in_geofence():
    zone = GeoFenceZone(
        zone_id="z",
        name="box",
        polygon=[
            GeoPoint(latitude=0.0, longitude=0.0),
            GeoPoint(latitude=0.0, longitude=1.0),
            GeoPoint(latitude=1.0, longitude=1.0),
            GeoPoint(latitude=1.0, longitude=0.0),
        ],
    )
    assert point_in_geofence(GeoPoint(latitude=0.5, longitude=0.5), zone) is True
    assert point_in_geofence(GeoPoint(latitude=5.0, longitude=5.0), zone) is False


def test_heatmap_severity_weighting(isolated_repo, monkeypatch):
    monkeypatch.setattr(
        gs,
        "load_gis_settings",
        lambda: {
            "heatmap": {
                "enabled": True,
                "radius_meters": 500,
                "severity_weights": {"low": 1, "medium": 3, "high": 7, "critical": 12},
            }
        },
    )

    def fake_markers(**kwargs):
        del kwargs
        from app.models.gis_models import EventGeoMarker

        return [
            EventGeoMarker(
                event_id="e1",
                source_type="live_stream",
                camera_id="c1",
                severity="low",
                latitude=10.0,
                longitude=20.0,
                timestamp="2026-01-01T00:00:00+00:00",
            ),
            EventGeoMarker(
                event_id="e2",
                source_type="live_stream",
                camera_id="c1",
                severity="critical",
                latitude=10.0001,
                longitude=20.0001,
                timestamp="2026-01-01T00:00:00+00:00",
            ),
        ]

    monkeypatch.setattr(isolated_repo, "get_event_markers", fake_markers)
    cells = compute_risk_heatmap(isolated_repo, _user("supervisor"), None, None, None, None, None, None, None)
    assert cells
    assert cells[0].weight >= cells[-1].weight


def test_geopy_matches_pyproj_order_of_magnitude():
    from pyproj import Geod

    p1 = GeoPoint(latitude=30.0, longitude=71.0)
    p2 = GeoPoint(latitude=30.001, longitude=71.0)
    d_geo = distance_meters(p1, p2)
    geod = Geod(ellps="WGS84")
    _, _, d_proj = geod.inv(p1.longitude, p1.latitude, p2.longitude, p2.latitude)
    assert abs(abs(float(d_proj)) - d_geo) < 5.0

