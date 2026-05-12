"""Tests for drone NED/geo coordinate conversion (Phase 45)."""
from __future__ import annotations

import math

import pytest

from app.services.drone.drone_coordinate_mapper import (
    HOME_LATITUDE,
    HOME_LONGITUDE,
    geo_to_ned,
    haversine_distance_meters,
    ned_to_geo,
)


class TestGeoToNED:
    def test_home_origin_returns_zero(self):
        ned = geo_to_ned(HOME_LATITUDE, HOME_LONGITUDE, 0.0)
        assert abs(ned.x) < 0.01
        assert abs(ned.y) < 0.01
        assert abs(ned.z) < 0.01

    def test_north_positive(self):
        ned = geo_to_ned(HOME_LATITUDE + 0.001, HOME_LONGITUDE, 0.0)
        assert ned.x > 0

    def test_east_positive(self):
        ned = geo_to_ned(HOME_LATITUDE, HOME_LONGITUDE + 0.001, 0.0)
        assert ned.y > 0

    def test_altitude_above_home_is_negative_z(self):
        ned = geo_to_ned(HOME_LATITUDE, HOME_LONGITUDE, 50.0)
        assert ned.z < 0  # above home → NED z is negative (down convention)


class TestNEDToGeo:
    def test_round_trip(self):
        lat, lon, alt = 30.160, 71.530, 45.0
        ned = geo_to_ned(lat, lon, alt)
        geo = ned_to_geo(ned.x, ned.y, ned.z)
        assert abs(geo.latitude - lat) < 0.0001
        assert abs(geo.longitude - lon) < 0.0001
        assert abs(geo.altitude_meters - alt) < 0.1

    def test_origin_round_trip(self):
        geo = ned_to_geo(0.0, 0.0, 0.0)
        assert abs(geo.latitude - HOME_LATITUDE) < 0.0001
        assert abs(geo.longitude - HOME_LONGITUDE) < 0.0001


class TestHaversineDistance:
    def test_zero_distance(self):
        d = haversine_distance_meters(30.1575, 71.5249, 30.1575, 71.5249)
        assert d == 0.0

    def test_known_approx_distance(self):
        # 0.01 degree latitude ≈ 1111 m
        d = haversine_distance_meters(30.0, 71.0, 30.01, 71.0)
        assert 1000 < d < 1200

    def test_symmetric(self):
        d1 = haversine_distance_meters(30.15, 71.52, 30.16, 71.53)
        d2 = haversine_distance_meters(30.16, 71.53, 30.15, 71.52)
        assert abs(d1 - d2) < 0.01
