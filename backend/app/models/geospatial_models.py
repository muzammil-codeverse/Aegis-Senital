from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GeoPoint:
    lat: float | None = None
    lng: float | None = None
    x: float | None = None
    y: float | None = None
    floor: int | None = None
    label: str | None = None

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "x": self.x,
            "y": self.y,
            "floor": self.floor,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GeoPoint":
        return cls(
            lat=d.get("lat"),
            lng=d.get("lng"),
            x=d.get("x"),
            y=d.get("y"),
            floor=d.get("floor"),
            label=d.get("label"),
        )


@dataclass
class GeoBounds:
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 1600.0
    y_max: float = 900.0
    lat_min: float | None = None
    lat_max: float | None = None
    lng_min: float | None = None
    lng_max: float | None = None

    def to_dict(self) -> dict:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "lat_min": self.lat_min,
            "lat_max": self.lat_max,
            "lng_min": self.lng_min,
            "lng_max": self.lng_max,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GeoBounds":
        return cls(
            x_min=float(d.get("x_min", 0)),
            y_min=float(d.get("y_min", 0)),
            x_max=float(d.get("x_max", 1600)),
            y_max=float(d.get("y_max", 900)),
            lat_min=d.get("lat_min"),
            lat_max=d.get("lat_max"),
            lng_min=d.get("lng_min"),
            lng_max=d.get("lng_max"),
        )


@dataclass
class MapSite:
    site_id: str
    name: str
    bounds: GeoBounds = field(default_factory=GeoBounds)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "bounds": self.bounds.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MapSite":
        return cls(
            site_id=str(d.get("site_id", "default")),
            name=str(d.get("name", "Site")),
            bounds=GeoBounds.from_dict(d.get("bounds") or {}),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class OperationalZone:
    zone_id: str
    name: str
    zone_type: str = "general"
    priority: str = "normal"
    polygon: list[list[float]] = field(default_factory=list)
    restricted: bool = False
    active_hours: list[int] = field(default_factory=lambda: [0, 24])
    allowed_objects: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "zone_type": self.zone_type,
            "priority": self.priority,
            "polygon": self.polygon,
            "restricted": self.restricted,
            "active_hours": self.active_hours,
            "allowed_objects": self.allowed_objects,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OperationalZone":
        return cls(
            zone_id=str(d.get("zone_id", "")),
            name=str(d.get("name", "")),
            zone_type=str(d.get("zone_type", "general")),
            priority=str(d.get("priority", "normal")),
            polygon=[[float(v) for v in pt] for pt in (d.get("polygon") or [])],
            restricted=bool(d.get("restricted", False)),
            active_hours=list(d.get("active_hours") or [0, 24]),
            allowed_objects=list(d.get("allowed_objects") or []),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class Geofence:
    geofence_id: str
    name: str
    zone_type: str = "geofence"
    polygon: list[list[float]] = field(default_factory=list)
    restricted: bool = True
    active: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "geofence_id": self.geofence_id,
            "name": self.name,
            "zone_type": self.zone_type,
            "polygon": self.polygon,
            "restricted": self.restricted,
            "active": self.active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_zone(cls, zone: OperationalZone) -> "Geofence":
        return cls(
            geofence_id=zone.zone_id,
            name=zone.name,
            zone_type=zone.zone_type,
            polygon=zone.polygon,
            restricted=zone.restricted,
            active=True,
            metadata=zone.metadata,
        )


@dataclass
class CameraMapNode:
    camera_id: str
    name: str
    status: str = "offline"
    priority: str = "normal"
    location: GeoPoint = field(default_factory=GeoPoint)
    zone: str | None = None
    fov_degrees: float = 90.0
    view_direction_degrees: float = 0.0
    coverage_radius: float = 150.0
    latest_alert_severity: str | None = None
    latest_frame_url: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "status": self.status,
            "priority": self.priority,
            "location": self.location.to_dict(),
            "zone": self.zone,
            "fov_degrees": self.fov_degrees,
            "view_direction_degrees": self.view_direction_degrees,
            "coverage_radius": self.coverage_radius,
            "latest_alert_severity": self.latest_alert_severity,
            "latest_frame_url": self.latest_frame_url,
            "metadata": self.metadata,
        }


@dataclass
class CameraConnection:
    from_camera: str
    to_camera: str
    distance_meters: float = 0.0
    min_travel_seconds: float = 0.0
    max_travel_seconds: float = 60.0
    transition_probability: float = 0.5
    bidirectional: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "from_camera": self.from_camera,
            "to_camera": self.to_camera,
            "distance_meters": self.distance_meters,
            "min_travel_seconds": self.min_travel_seconds,
            "max_travel_seconds": self.max_travel_seconds,
            "transition_probability": self.transition_probability,
            "bidirectional": self.bidirectional,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CameraConnection":
        return cls(
            from_camera=str(d.get("from_camera") or d.get("from", "")),
            to_camera=str(d.get("to_camera") or d.get("to", "")),
            distance_meters=float(d.get("distance_meters", 0)),
            min_travel_seconds=float(d.get("min_travel_seconds", 0)),
            max_travel_seconds=float(d.get("max_travel_seconds", 60)),
            transition_probability=float(d.get("transition_probability", 0.5)),
            bidirectional=bool(d.get("bidirectional", False)),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class MapIncidentMarker:
    incident_id: str
    incident_type: str = "unknown"
    severity: str = "medium"
    location: GeoPoint = field(default_factory=GeoPoint)
    camera_id: str | None = None
    timestamp: float | None = None
    status: str = "active"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "location": self.location.to_dict(),
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "metadata": self.metadata,
        }


@dataclass
class MapAlertMarker:
    alert_id: str
    title: str = ""
    severity: str = "medium"
    location: GeoPoint = field(default_factory=GeoPoint)
    camera_id: str | None = None
    timestamp: float | None = None
    state: str = "active"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "severity": self.severity,
            "location": self.location.to_dict(),
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "state": self.state,
            "metadata": self.metadata,
        }
