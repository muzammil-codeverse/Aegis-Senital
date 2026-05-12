from __future__ import annotations

from pathlib import Path

import pytest

from app.models.gis_models import CameraGeoProfile, GeoFenceZone, GeoPoint
from app.models.security_models import UserAccount, UserStatus
from app.repositories import gis_repository as gr


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
    cam = tmp_path / "camera_geo_profiles.jsonl"
    geo = tmp_path / "geofences.jsonl"
    monkeypatch.setattr(gr, "_camera_profiles_path", lambda: cam)
    monkeypatch.setattr(gr, "_geofences_path", lambda: geo)
    gr.reset_gis_repository_singleton()
    yield gr.get_gis_repository()
    gr.reset_gis_repository_singleton()


def test_upsert_and_get_camera(isolated_repo):
    p = CameraGeoProfile(
        camera_id="cam_a",
        name="A",
        latitude=30.0,
        longitude=71.0,
        heading_degrees=0.0,
        fov_degrees=60.0,
        coverage_radius_meters=50.0,
    )
    isolated_repo.upsert_camera_geo_profile(p)
    loaded = isolated_repo.get_camera_geo_profile("cam_a")
    assert loaded is not None
    assert loaded.latitude == 30.0


def test_list_cameras_filters_scope(isolated_repo):
    isolated_repo.upsert_camera_geo_profile(
        CameraGeoProfile(camera_id="cam_x", name="x", latitude=1.0, longitude=1.0)
    )
    scoped = _user("analyst", camera_scopes=["cam_x"])
    items = isolated_repo.list_camera_geo_profiles(scoped)
    assert any(c.camera_id == "cam_x" for c in items)
    denied = _user("analyst", camera_scopes=["other"])
    assert isolated_repo.list_camera_geo_profiles(denied) == []


def test_geofence_crud(isolated_repo):
    z = GeoFenceZone(
        zone_id="zone_t1",
        name="Restricted Gate Area",
        zone_type="restricted",
        polygon=[
            GeoPoint(latitude=30.157, longitude=71.524),
            GeoPoint(latitude=30.158, longitude=71.525),
            GeoPoint(latitude=30.156, longitude=71.526),
        ],
        severity="high",
    )
    isolated_repo.create_geofence(z)
    assert isolated_repo.get_geofence("zone_t1") is not None
    isolated_repo.update_geofence("zone_t1", {"name": "Renamed"})
    assert isolated_repo.get_geofence("zone_t1").name == "Renamed"
    assert isolated_repo.delete_geofence("zone_t1") is True
    assert isolated_repo.get_geofence("zone_t1") is None
