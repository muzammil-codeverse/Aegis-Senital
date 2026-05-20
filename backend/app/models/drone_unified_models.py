"""Phase 8 — Unified drone operational state model.

Merges registry state (CityDrone), scenario dispatch context (ScenarioRun),
Phase 7 DroneRoute tracking, and AirSim provider health into a single
read-only snapshot. All instances are simulated=True. No real hardware.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DroneRegistryStatus(str, Enum):
    """Status as reported by the city surveillance registry (CityDrone.status)."""
    STANDBY = "standby"
    AIRBORNE = "airborne"
    RETURNING = "returning"
    CHARGING = "charging"
    OFFLINE = "offline"
    MISSION = "mission"


class DroneRoutePhase(str, Enum):
    """Current phase of the active scenario route."""
    NONE = "none"
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    TRACKING = "tracking"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DroneProviderStatus(str, Enum):
    """AirSim / CosysAirSim provider connectivity."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ProviderState(BaseModel):
    """Snapshot of the AirSim provider connection as seen by the cosys_airsim_client."""
    model_config = ConfigDict(extra="ignore")

    provider: str = "cosys_airsim"
    status: DroneProviderStatus = DroneProviderStatus.UNKNOWN
    simulator_connected: bool = False
    telemetry_available: bool = False
    frame_available: bool = False
    endpoint: str | None = None
    last_error: str | None = None
    checked_at: str = Field(default_factory=_now_iso)


class DroneMissionState(BaseModel):
    """Active mission plan details when a drone has been assigned to a mission."""
    model_config = ConfigDict(extra="ignore")

    mission_id: str
    mission_name: str = "Simulated Aerial Patrol Mission"
    mission_status: str = "executing"
    current_waypoint_index: int = 0
    progress_percent: float = 0.0
    simulated: bool = True
    operator_review_required: bool = True
    started_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Primary unified model
# ---------------------------------------------------------------------------

class UnifiedDroneState(BaseModel):
    """Merged operational snapshot for a single drone.

    Fields are populated from three sources:
    - Registry: drone_id, name, registry_status, assigned_zone, battery_percent,
                current_location, home_location, camera_feed_uri, capabilities
    - Scenario engine: active_scenario_run_id, active_route_id, route_status,
                       dispatched_at, linked_actor_id
    - AirSim provider: provider_status (provider_state sub-model)
    """
    model_config = ConfigDict(extra="ignore")

    # Identity
    drone_id: str
    name: str = ""
    simulated: bool = True

    # Registry layer
    registry_status: DroneRegistryStatus = DroneRegistryStatus.STANDBY
    assigned_zone: str = ""
    battery_percent: float = 100.0
    current_location: dict[str, Any] = Field(default_factory=dict)
    home_location: dict[str, Any] = Field(default_factory=dict)
    camera_feed_uri: str = ""
    capabilities: list[str] = Field(default_factory=list)

    # Mission layer (DroneMissionPlan / DroneMissionSession)
    active_mission_id: str | None = None
    mission_status: str | None = None
    mission_state: DroneMissionState | None = None

    # Scenario route layer (Phase 7 DroneRoute)
    active_scenario_run_id: str | None = None
    active_route_id: str | None = None
    route_status: DroneRoutePhase = DroneRoutePhase.NONE
    linked_actor_id: str | None = None
    dispatched_at: str | None = None

    # Provider layer (AirSim)
    provider_status: DroneProviderStatus = DroneProviderStatus.UNKNOWN
    provider_state: ProviderState = Field(default_factory=ProviderState)
    telemetry_source: str = "registry"

    # Timestamps
    last_observation_at: str | None = None
    last_updated_at: str = Field(default_factory=_now_iso)

    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Response wrapper
# ---------------------------------------------------------------------------

class UnifiedFleetState(BaseModel):
    """Full fleet snapshot returned by the unified drone state endpoint."""
    model_config = ConfigDict(extra="ignore")

    drones: list[UnifiedDroneState] = Field(default_factory=list)
    total: int = 0
    provider_connected: bool = False
    generated_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)
