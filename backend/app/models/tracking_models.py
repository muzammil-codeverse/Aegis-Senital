from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    SUSPECT = "suspect"
    DRONE = "drone"
    CAMERA_OBSERVATION = "camera_observation"
    VEHICLE = "vehicle"


class DroneRouteStatus(str, Enum):
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    TRACKING = "tracking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class FusedTrackStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    LOST = "lost"


class WaypointLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: float = 0.0
    y: float = 0.0
    z: float | None = None
    lat: float | None = None
    lng: float | None = None


class PathWaypoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    waypoint_id: str
    entity_id: str
    entity_type: EntityType
    offset_seconds: int
    location: WaypointLocation = Field(default_factory=WaypointLocation)
    zone_id: str | None = None
    zone_name: str | None = None
    source_id: str | None = None
    source_type: str | None = None
    confidence: float = 0.85
    metadata: dict[str, Any] = Field(default_factory=dict)


class CameraHandoff(BaseModel):
    model_config = ConfigDict(extra="ignore")

    handoff_id: str
    scenario_run_id: str
    from_camera_id: str
    to_camera_id: str
    actor_id: str
    offset_seconds: int
    reason: str = "suspect_movement"
    confidence: float = 0.85
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusedTrack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    track_id: str
    scenario_run_id: str
    actor_id: str
    source_types: list[str] = Field(default_factory=list)
    waypoints: list[PathWaypoint] = Field(default_factory=list)
    camera_observations: list[dict[str, Any]] = Field(default_factory=list)
    drone_observations: list[dict[str, Any]] = Field(default_factory=list)
    handoffs: list[CameraHandoff] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    incident_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.85
    status: FusedTrackStatus = FusedTrackStatus.ACTIVE
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneRoute(BaseModel):
    model_config = ConfigDict(extra="ignore")

    route_id: str
    scenario_run_id: str
    drone_id: str
    mission_id: str | None = None
    waypoints: list[PathWaypoint] = Field(default_factory=list)
    status: DroneRouteStatus = DroneRouteStatus.PLANNED
    linked_actor_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
