from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GeoSourceType = Literal["live_stream", "uploaded_video", "drone_simulation", "drone_mission"]
ZoneType = Literal["restricted", "patrol", "safe", "high_risk"]
SeverityLevel = Literal["low", "medium", "high", "critical"]


class GeoPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    altitude_meters: float | None = None

    @field_validator("latitude")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not (-90.0 <= float(v) <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return float(v)

    @field_validator("longitude")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not (-180.0 <= float(v) <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return float(v)


class CameraGeoProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    name: str = ""
    latitude: float
    longitude: float
    altitude_meters: float | None = None
    heading_degrees: float = 0.0
    fov_degrees: float = 75.0
    coverage_radius_meters: float = 80.0
    floor_level: str | None = None
    region: str | None = None
    is_public_location: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("latitude")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not (-90.0 <= float(v) <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return float(v)

    @field_validator("longitude")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not (-180.0 <= float(v) <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return float(v)


class CameraFieldOfView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    polygon: list[GeoPoint]
    heading_degrees: float
    fov_degrees: float
    coverage_radius_meters: float


class EventGeoMarker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    source_type: GeoSourceType | str = "live_stream"
    camera_id: str | None = None
    case_id: str | None = None
    event_type: str = "possible_incident"
    severity: str = "medium"
    latitude: float
    longitude: float
    altitude_meters: float | None = None
    timestamp: str
    risk_score: float | None = None
    operator_review_required: bool = True
    title: str | None = Field(default=None, description="Safe wording for UI")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("latitude")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not (-90.0 <= float(v) <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return float(v)

    @field_validator("longitude")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not (-180.0 <= float(v) <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return float(v)


class CaseGeoMarker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    title: str
    severity: str = "medium"
    latitude: float
    longitude: float
    primary_camera_id: str | None = None
    updated_at: str | None = None
    operator_review_required: bool = True

    @field_validator("latitude")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not (-90.0 <= float(v) <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return float(v)

    @field_validator("longitude")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not (-180.0 <= float(v) <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return float(v)


class RiskHeatmapCell(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cell_id: str
    center_latitude: float
    center_longitude: float
    weight: float
    event_count: int = 0
    severity: str | None = None


class GeoFenceZone(BaseModel):
    model_config = ConfigDict(extra="ignore")

    zone_id: str
    name: str
    zone_type: ZoneType | str = "restricted"
    polygon: list[GeoPoint]
    severity: SeverityLevel | str = "high"
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeoFenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    zone_type: ZoneType | str = "restricted"
    polygon: list[GeoPoint]
    severity: SeverityLevel | str = "high"
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeoFenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    zone_type: ZoneType | str | None = None
    polygon: list[GeoPoint] | None = None
    severity: SeverityLevel | str | None = None
    active: bool | None = None
    metadata: dict[str, Any] | None = None


class MapViewportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    north: float | None = None
    south: float | None = None
    east: float | None = None
    west: float | None = None
    zoom: float | None = None


class DronePathOverlay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    drone_id: str
    source_type: str = "drone_simulation"
    simulated: bool = True
    points: list[GeoPoint] = Field(default_factory=list)
    latest_timestamp: str | None = None


class MapLayerResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cameras: list[CameraGeoProfile] = Field(default_factory=list)
    camera_fovs: list[CameraFieldOfView] = Field(default_factory=list)
    event_markers: list[EventGeoMarker] = Field(default_factory=list)
    case_markers: list[CaseGeoMarker] = Field(default_factory=list)
    heatmap_cells: list[RiskHeatmapCell] = Field(default_factory=list)
    geofences: list[GeoFenceZone] = Field(default_factory=list)
    drone_paths: list[DronePathOverlay] = Field(default_factory=list)
    drone_mission_routes: list[dict[str, Any]] = Field(default_factory=list)
    drone_mission_waypoints: list[dict[str, Any]] = Field(default_factory=list)
    active_mission_paths: list[dict[str, Any]] = Field(default_factory=list)
    completed_mission_paths: list[dict[str, Any]] = Field(default_factory=list)
    stream_status_by_camera: dict[str, Any] = Field(default_factory=dict)
    viewport: MapViewportRequest | None = None


class NearbyCameraQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    radius_meters: float = 500.0


class NearbyCameraResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    camera_id: str
    name: str = ""
    distance_meters: float
    latitude: float
    longitude: float


class GisPublicConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    provider: str = "local_mock"
    map: dict[str, Any] = Field(default_factory=dict)
    cameras: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    heatmap: dict[str, Any] = Field(default_factory=dict)
    geofencing: dict[str, Any] = Field(default_factory=dict)
    frontend: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def _lower_provider(cls, v: Any) -> str:
        return str(v or "local_mock").strip().lower()
