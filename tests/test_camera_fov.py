from __future__ import annotations

from app.models.gis_models import CameraGeoProfile
from app.services.gis_service import compute_camera_fov_polygon


def test_camera_fov_closed_ring():
    p = CameraGeoProfile(
        camera_id="c",
        name="n",
        latitude=20.0,
        longitude=30.0,
        heading_degrees=180.0,
        fov_degrees=90.0,
        coverage_radius_meters=200.0,
    )
    poly = compute_camera_fov_polygon(p)
    assert poly[0].latitude == poly[-1].latitude
    assert poly[0].longitude == poly[-1].longitude
