"""Tests for drone mission GIS layer integration (Phase 45)."""
from __future__ import annotations

import pytest
from app.models.gis_models import MapLayerResponse, GeoSourceType


class TestGisModelExtensions:
    def test_map_layer_response_has_mission_fields(self):
        layer = MapLayerResponse()
        assert hasattr(layer, "drone_mission_routes")
        assert hasattr(layer, "drone_mission_waypoints")
        assert hasattr(layer, "active_mission_paths")
        assert hasattr(layer, "completed_mission_paths")

    def test_mission_route_layer_is_list(self):
        layer = MapLayerResponse()
        assert isinstance(layer.drone_mission_routes, list)
        assert isinstance(layer.drone_mission_waypoints, list)

    def test_drone_mission_source_type(self):
        # "drone_mission" should be a valid GeoSourceType
        # We test by importing and using it in a model context
        from app.models.gis_models import GeoPoint
        # GeoSourceType includes "drone_mission"
        assert "drone_mission" in GeoSourceType.__args__

    def test_mission_routes_can_hold_dicts(self):
        route_data = {"mission_id": "m1", "waypoints": [], "simulated": True}
        layer = MapLayerResponse(drone_mission_routes=[route_data])
        assert len(layer.drone_mission_routes) == 1
        assert layer.drone_mission_routes[0]["mission_id"] == "m1"
