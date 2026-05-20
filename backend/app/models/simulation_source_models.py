from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SimSourceType(str, Enum):
    FIXED_CCTV = "fixed_cctv"
    PTZ_CAMERA = "ptz_camera"
    DRONE_CAMERA = "drone_camera"
    SIMULATION_VIRTUAL = "simulation_virtual_camera"
    UPLOADED_VIDEO = "uploaded_video_source"
    SCENARIO_OBSERVATION = "scenario_observation_source"


class SimCameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class SimDroneStatus(str, Enum):
    STANDBY = "standby"
    AIRBORNE = "airborne"
    RETURNING = "returning"
    CHARGING = "charging"
    OFFLINE = "offline"
    MISSION = "mission"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CityLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    x: float = 0.0
    y: float = 0.0
    z: float | None = None
    latitude: float | None = None
    longitude: float | None = None


class CameraOrientation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    yaw: float = 0.0
    pitch: float | None = None
    roll: float | None = None


class CameraCoverage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    range_meters: float = 50.0
    fov_degrees: float = 90.0
    direction: str = "north"


class CityCamera(BaseModel):
    model_config = ConfigDict(extra="ignore")
    camera_id: str
    name: str
    source_type: SimSourceType = SimSourceType.FIXED_CCTV
    zone_id: str
    zone_name: str
    district: str
    location: CityLocation = Field(default_factory=CityLocation)
    orientation: CameraOrientation = Field(default_factory=CameraOrientation)
    coverage: CameraCoverage = Field(default_factory=CameraCoverage)
    feed_uri: str = ""
    status: SimCameraStatus = SimCameraStatus.ONLINE
    priority: str = "normal"
    linked_scenarios: list[str] = Field(default_factory=list)
    supported_detections: list[str] = Field(default_factory=list)
    dashboard_pinned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    last_observation_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CityCamera":
        return cls.model_validate(data)


class CityDrone(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drone_id: str
    name: str
    status: SimDroneStatus = SimDroneStatus.STANDBY
    assigned_zone: str
    current_location: CityLocation = Field(default_factory=CityLocation)
    home_location: CityLocation = Field(default_factory=CityLocation)
    camera_feed_uri: str = ""
    battery_percent: float = 100.0
    mission_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CityDrone":
        return cls.model_validate(data)


class SimulationObservationRequest(BaseModel):
    """Structured simulation observation for source-governed intelligence ingestion."""
    model_config = ConfigDict(extra="ignore")
    source_type: Literal["simulation_cctv", "drone_camera", "scenario_observation"] = "simulation_cctv"
    camera_id: str | None = None
    drone_id: str | None = None
    zone: str | None = None
    event_type: str = "suspicious_person"
    confidence: float = 0.75
    severity: str = "medium"
    description: str = ""
    frame_index: int | None = None
    bounding_box: dict[str, Any] | list[float] | None = None
    detected_class: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DashboardFeedEntry(BaseModel):
    """Camera entry returned by the dashboard-feeds endpoint."""
    model_config = ConfigDict(extra="ignore")
    camera_id: str
    name: str
    zone_id: str
    zone_name: str
    district: str
    location: CityLocation = Field(default_factory=CityLocation)
    orientation: CameraOrientation = Field(default_factory=CameraOrientation)
    coverage: CameraCoverage = Field(default_factory=CameraCoverage)
    status: SimCameraStatus
    source_type: SimSourceType
    feed_uri: str
    priority: str
    supported_detections: list[str] = Field(default_factory=list)
    dashboard_pinned: bool = False
    last_observation_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
