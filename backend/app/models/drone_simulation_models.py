from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DroneConnectionState = Literal["connected", "disconnected", "degraded"]
DroneSessionState = Literal["idle", "starting", "running", "stopping", "stopped", "error", "degraded"]
DroneCommandName = Literal["takeoff", "land", "move_to_position", "hover"]
DroneObservationType = Literal["telemetry", "frame", "detection", "transition"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DroneBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class DronePose(DroneBaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class DroneOrientation(DroneBaseModel):
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0


class DroneConnectionStatus(DroneBaseModel):
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    status: DroneConnectionState = "disconnected"
    connected: bool = False
    endpoint: str | None = None
    vehicle_name: str | None = None
    camera_name: str | None = None
    checked_at: str = Field(default_factory=_now_iso)
    last_error: str | None = None


class DroneTelemetry(DroneBaseModel):
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    timestamp: str = Field(default_factory=_now_iso)
    latitude: float | None = None
    longitude: float | None = None
    altitude_meters: float | None = None
    position: DronePose = Field(default_factory=DronePose)
    velocity: DronePose = Field(default_factory=DronePose)
    orientation: DroneOrientation = Field(default_factory=DroneOrientation)
    camera_name: str = "front_center"
    status: DroneConnectionState = "disconnected"
    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneCameraFrame(DroneBaseModel):
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    timestamp: str = Field(default_factory=_now_iso)
    frame_index: int = 0
    camera_name: str = "front_center"
    width: int = 0
    height: int = 0
    content_type: str = "image/jpeg"
    image_base64: str | None = None
    status: DroneConnectionState = "disconnected"
    frame_available: bool = False
    telemetry: DroneTelemetry | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None


class DroneSimulationSession(DroneBaseModel):
    session_id: str
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    status: DroneSessionState = "idle"
    active: bool = False
    started_at: str | None = None
    stopped_at: str | None = None
    updated_at: str = Field(default_factory=_now_iso)
    operator_id: str | None = None
    operator_name: str | None = None
    frame_index: int = 0
    frames_processed_total: int = 0
    telemetry_updates_total: int = 0
    allow_multiple: bool = False
    stream_processor_enabled: bool = True
    last_error: str | None = None


class DroneFlightPathPoint(DroneBaseModel):
    drone_id: str = "drone_sim_01"
    source_type: str = "drone_simulation"
    camera_id: str = "drone_sim_01"
    simulated: bool = True
    timestamp: str = Field(default_factory=_now_iso)
    latitude: float
    longitude: float
    altitude_meters: float | None = None
    position: DronePose = Field(default_factory=DronePose)
    orientation: DroneOrientation = Field(default_factory=DroneOrientation)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("latitude")
    @classmethod
    def _lat(cls, value: float) -> float:
        if not (-90.0 <= float(value) <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return float(value)

    @field_validator("longitude")
    @classmethod
    def _lon(cls, value: float) -> float:
        if not (-180.0 <= float(value) <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return float(value)


class DroneCommandRequest(DroneBaseModel):
    command: DroneCommandName
    x: float | None = None
    y: float | None = None
    z: float | None = None
    velocity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneCommandResponse(DroneBaseModel):
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    command: DroneCommandName
    success: bool = False
    status: str = "failed"
    detail: str | None = None
    issued_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneHealthStatus(DroneBaseModel):
    enabled: bool = True
    provider: str = "cosys_airsim"
    status: Literal["healthy", "disconnected", "degraded"] = "disconnected"
    simulator_connected: bool = False
    telemetry_available: bool = False
    frame_available: bool = False
    active_session: bool = False
    checked_at: str = Field(default_factory=_now_iso)
    last_error: str | None = None


class DroneObservationEvent(DroneBaseModel):
    event_id: str
    observation_type: DroneObservationType = "telemetry"
    source_type: str = "drone_simulation"
    source_id: str = "drone_sim_01"
    drone_id: str = "drone_sim_01"
    simulated: bool = True
    timestamp: str = Field(default_factory=_now_iso)
    latitude: float | None = None
    longitude: float | None = None
    altitude_meters: float | None = None
    confidence: float = 0.5
    safe_label: str = "Simulated aerial observation"
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
