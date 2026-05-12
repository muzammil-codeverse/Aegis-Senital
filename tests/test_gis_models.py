from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.gis_models import CameraGeoProfile, GeoFenceZone, GeoPoint


def test_geo_point_valid():
    p = GeoPoint(latitude=30.0, longitude=71.0)
    assert p.latitude == 30.0


def test_camera_profile_from_dict():
    p = CameraGeoProfile.model_validate(
        {
            "camera_id": "cam_01",
            "name": "Main Gate Camera",
            "latitude": 30.1575,
            "longitude": 71.5249,
            "altitude_meters": 12.0,
            "heading_degrees": 90.0,
            "fov_degrees": 75.0,
            "coverage_radius_meters": 80.0,
            "floor_level": None,
            "region": "main_gate",
            "is_public_location": False,
            "metadata": {},
        }
    )
    assert p.camera_id == "cam_01"


def test_invalid_latitude_rejected():
    with pytest.raises(ValidationError):
        CameraGeoProfile.model_validate(
            {
                "camera_id": "x",
                "latitude": 95,
                "longitude": 0,
            }
        )


def test_geofence_polygon_min_points():
    z = GeoFenceZone(
        zone_id="zone_1",
        name="z",
        polygon=[
            GeoPoint(latitude=30.0, longitude=71.0),
            GeoPoint(latitude=30.01, longitude=71.0),
            GeoPoint(latitude=30.01, longitude=71.01),
        ],
    )
    assert len(z.polygon) == 3
