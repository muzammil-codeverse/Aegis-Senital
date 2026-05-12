"""Geo <-> NED coordinate conversion for Cosys-AirSim drone missions (Phase 45).

Home coordinates match the default Cosys-AirSim environment origin used in
this project.  All coordinates are simulated; no real-world deployment implied.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.gis_models import GeoPoint

# Default home origin (Multan area — simulation environment anchor)
HOME_LATITUDE: float = 30.1575
HOME_LONGITUDE: float = 71.5249
HOME_ALTITUDE: float = 0.0

# Earth radius in metres
_EARTH_RADIUS_M: float = 6_371_000.0


@dataclass
class NEDPoint:
    """North-East-Down position relative to the home origin."""
    x: float  # North (metres)
    y: float  # East (metres)
    z: float  # Down (metres — positive = below home altitude)


def geo_to_ned(
    latitude: float,
    longitude: float,
    altitude: float,
    home_lat: float = HOME_LATITUDE,
    home_lon: float = HOME_LONGITUDE,
    home_alt: float = HOME_ALTITUDE,
) -> NEDPoint:
    """Convert WGS-84 geodetic coordinates to NED relative to home.

    Uses the equirectangular approximation, which is accurate to < 0.1 %
    within the typical simulation radius (< 5 km from home).

    Args:
        latitude: Target latitude in decimal degrees.
        longitude: Target longitude in decimal degrees.
        altitude: Target altitude in metres (MSL).
        home_lat: Home latitude in decimal degrees.
        home_lon: Home longitude in decimal degrees.
        home_alt: Home altitude in metres (MSL).

    Returns:
        NEDPoint with x=North, y=East, z=Down offsets in metres.
    """
    dlat = math.radians(latitude - home_lat)
    dlon = math.radians(longitude - home_lon)
    lat_mid = math.radians((latitude + home_lat) / 2.0)

    north = dlat * _EARTH_RADIUS_M
    east = dlon * _EARTH_RADIUS_M * math.cos(lat_mid)
    down = -(altitude - home_alt)  # NED convention: down is positive below origin

    return NEDPoint(x=north, y=east, z=down)


def ned_to_geo(
    x: float,
    y: float,
    z: float,
    home_lat: float = HOME_LATITUDE,
    home_lon: float = HOME_LONGITUDE,
    home_alt: float = HOME_ALTITUDE,
) -> GeoPoint:
    """Convert NED coordinates (relative to home) back to WGS-84.

    Args:
        x: North offset in metres.
        y: East offset in metres.
        z: Down offset in metres (positive = below home).
        home_lat: Home latitude in decimal degrees.
        home_lon: Home longitude in decimal degrees.
        home_alt: Home altitude in metres (MSL).

    Returns:
        GeoPoint with latitude, longitude, altitude_meters populated.
    """
    dlat = x / _EARTH_RADIUS_M
    lat_mid = math.radians(home_lat + math.degrees(dlat) / 2.0)
    cos_lat = math.cos(lat_mid)

    if abs(cos_lat) < 1e-10:
        dlon = 0.0
    else:
        dlon = y / (_EARTH_RADIUS_M * cos_lat)

    latitude = home_lat + math.degrees(dlat)
    longitude = home_lon + math.degrees(dlon)
    altitude = home_alt + (-z)  # NED down = negative altitude change

    return GeoPoint(latitude=latitude, longitude=longitude, altitude_meters=altitude)


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Return the great-circle distance in metres between two WGS-84 points."""
    r = _EARTH_RADIUS_M
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
