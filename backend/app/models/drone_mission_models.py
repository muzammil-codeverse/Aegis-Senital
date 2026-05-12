"""Pydantic models for the Drone Patrol Mission Planner (Phase 45).

All missions are simulated-only. No real-world deployment is represented.
All artifacts carry simulated=True and operator_review_required=True.
Safe wording is enforced: never "target confirmed", "suspect confirmed", etc.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "mission") -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DroneMissionStatus(str, Enum):
    """Lifecycle states of a simulated drone patrol mission."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DroneMissionRouteType(str, Enum):
    """Patrol route topology."""
    LINEAR = "linear"
    LOOP = "loop"
    RETURN_TO_HOME = "return_to_home"


class DroneWaypointCameraAction(str, Enum):
    """What the simulated camera should do at this waypoint."""
    NONE = "none"
    CAPTURE_FRAME = "capture_frame"
    RECORD_CLIP = "record_clip"
    HOVER_AND_OBSERVE = "hover_and_observe"


class DroneMissionEventType(str, Enum):
    """Event categories produced during a simulated patrol session."""
    MISSION_STARTED = "mission_started"
    MISSION_PAUSED = "mission_paused"
    MISSION_RESUMED = "mission_resumed"
    MISSION_COMPLETED = "mission_completed"
    MISSION_CANCELLED = "mission_cancelled"
    MISSION_FAILED = "mission_failed"
    WAYPOINT_REACHED = "waypoint_reached"
    WAYPOINT_SKIPPED = "waypoint_skipped"
    OBSERVATION_RECORDED = "observation_recorded"
    GEOFENCE_VIOLATION = "geofence_violation"
    SIMULATOR_DISCONNECTED = "simulator_disconnected"
    OPERATOR_OVERRIDE = "operator_override"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

class DroneMissionBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------

class DroneWaypoint(DroneMissionBaseModel):
    """A single geographic position in a simulated patrol route."""

    waypoint_id: str = Field(default_factory=lambda: _new_id("wp"))
    sequence_index: int = 0
    latitude: float
    longitude: float
    altitude_meters: float = 40.0
    velocity_mps: float = 5.0
    hold_seconds: float = 0.0
    camera_action: DroneWaypointCameraAction = DroneWaypointCameraAction.NONE
    label: str | None = None
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

    @field_validator("altitude_meters")
    @classmethod
    def _alt(cls, v: float) -> float:
        if float(v) <= 0:
            raise ValueError("altitude_meters must be > 0")
        return float(v)

    @field_validator("velocity_mps")
    @classmethod
    def _vel(cls, v: float) -> float:
        if float(v) <= 0:
            raise ValueError("velocity_mps must be > 0")
        return float(v)


class DronePatrolRoute(DroneMissionBaseModel):
    """Ordered collection of waypoints forming a patrol route."""

    route_id: str = Field(default_factory=lambda: _new_id("route"))
    name: str = "Simulated Patrol Route"
    route_type: DroneMissionRouteType = DroneMissionRouteType.LINEAR
    waypoints: list[DroneWaypoint] = Field(default_factory=list)
    estimated_distance_meters: float | None = None
    estimated_duration_seconds: float | None = None
    simulated: bool = True
    operator_review_required: bool = True
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionPlan(DroneMissionBaseModel):
    """Full simulated drone patrol mission plan."""

    mission_id: str = Field(default_factory=lambda: _new_id("mission"))
    name: str = "Simulated Aerial Patrol Mission"
    description: str | None = None
    simulated: bool = True
    provider: str = "cosys_airsim"

    # Route
    route_type: DroneMissionRouteType = DroneMissionRouteType.LINEAR
    waypoints: list[DroneWaypoint] = Field(default_factory=list)

    # Assignment
    assigned_drone_id: str = "drone_sim_01"
    created_by: str | None = None

    # Lifecycle
    status: DroneMissionStatus = DroneMissionStatus.DRAFT
    operator_review_required: bool = True
    operator_approved_by: str | None = None
    operator_approved_at: str | None = None

    # Estimates (populated by planning service)
    estimated_distance_meters: float | None = None
    estimated_duration_seconds: float | None = None

    # Timestamps
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    # Safety labels — never use real-world claims
    safe_label: str = "Candidate patrol route — operator review required"

    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionSession(DroneMissionBaseModel):
    """Active execution session for a simulated drone patrol mission."""

    session_id: str = Field(default_factory=lambda: _new_id("session"))
    mission_id: str
    drone_id: str = "drone_sim_01"
    provider: str = "cosys_airsim"
    simulated: bool = True
    operator_review_required: bool = True

    # State
    status: DroneMissionStatus = DroneMissionStatus.DRAFT
    current_waypoint_index: int = 0
    progress_percent: float = 0.0
    total_waypoints: int = 0

    # Timestamps
    started_at: str | None = None
    paused_at: str | None = None
    resumed_at: str | None = None
    completed_at: str | None = None
    updated_at: str = Field(default_factory=_now_iso)

    # Counters
    telemetry_count: int = 0
    event_count: int = 0
    waypoints_reached: int = 0

    # Error tracking
    last_error: str | None = None

    # Operator info
    started_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionCommand(DroneMissionBaseModel):
    """A lifecycle command issued against a simulated mission session."""

    command: Literal["start", "pause", "resume", "cancel"]
    issued_by: str | None = None
    reason: str | None = None
    issued_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionTelemetryPoint(DroneMissionBaseModel):
    """A single telemetry snapshot during simulated mission execution."""

    telemetry_id: str = Field(default_factory=lambda: _new_id("telem"))
    session_id: str
    mission_id: str
    drone_id: str = "drone_sim_01"
    simulated: bool = True
    timestamp: str = Field(default_factory=_now_iso)

    # Position
    latitude: float | None = None
    longitude: float | None = None
    altitude_meters: float | None = None

    # NED coordinates (relative to home)
    ned_x: float | None = None
    ned_y: float | None = None
    ned_z: float | None = None

    # Motion
    velocity_x: float | None = None
    velocity_y: float | None = None
    velocity_z: float | None = None
    heading_degrees: float | None = None

    # Mission progress
    current_waypoint_index: int = 0
    progress_percent: float = 0.0

    # Status
    mission_status: DroneMissionStatus = DroneMissionStatus.EXECUTING

    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionEvent(DroneMissionBaseModel):
    """A discrete event that occurred during a simulated mission session."""

    event_id: str = Field(default_factory=lambda: _new_id("event"))
    session_id: str
    mission_id: str
    drone_id: str = "drone_sim_01"
    simulated: bool = True
    operator_review_required: bool = True
    timestamp: str = Field(default_factory=_now_iso)

    event_type: DroneMissionEventType
    waypoint_index: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_meters: float | None = None

    # Safe wording — never use real-world confirmation phrases
    safe_label: str = "Simulated aerial patrol observation"
    detail: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionReport(DroneMissionBaseModel):
    """Post-mission summary report for a simulated patrol."""

    report_id: str = Field(default_factory=lambda: _new_id("report"))
    session_id: str
    mission_id: str
    drone_id: str = "drone_sim_01"
    simulated: bool = True
    operator_review_required: bool = True
    generated_at: str = Field(default_factory=_now_iso)

    # Outcome
    mission_status: DroneMissionStatus = DroneMissionStatus.COMPLETED
    total_waypoints: int = 0
    waypoints_reached: int = 0
    completion_percent: float = 0.0

    # Duration
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None

    # Path
    telemetry_count: int = 0
    event_count: int = 0
    estimated_distance_meters: float | None = None

    # Summary text — safe wording only
    summary: str = "Simulated aerial patrol mission report. Operator review required before any operational use."

    # Evidence refs
    telemetry_manifest_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionReplay(DroneMissionBaseModel):
    """Replay data bundle for a completed simulated patrol mission."""

    replay_id: str = Field(default_factory=lambda: _new_id("replay"))
    session_id: str
    mission_id: str
    simulated: bool = True
    generated_at: str = Field(default_factory=_now_iso)

    # Telemetry path for map replay
    include_telemetry_path: bool = True
    telemetry_points: list[DroneMissionTelemetryPoint] = Field(default_factory=list)

    # Events
    events: list[DroneMissionEvent] = Field(default_factory=list)

    # Report
    report: DroneMissionReport | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class DroneMissionCreateRequest(DroneMissionBaseModel):
    """Request body for creating a new simulated drone patrol mission."""

    name: str = "Simulated Aerial Patrol Mission"
    description: str | None = None
    route_type: DroneMissionRouteType = DroneMissionRouteType.LINEAR
    waypoints: list[DroneWaypoint]
    assigned_drone_id: str = "drone_sim_01"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionStartRequest(DroneMissionBaseModel):
    """Request body for starting a mission execution session."""

    mission_id: str
    operator_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionReviewRecord(DroneMissionBaseModel):
    """Operator review record attached to a mission plan or session."""

    review_id: str = Field(default_factory=lambda: _new_id("review"))
    mission_id: str
    session_id: str | None = None
    reviewed_by: str
    decision: Literal["approved", "rejected", "deferred"]
    notes: str | None = None
    simulated: bool = True
    operator_review_required: bool = True
    reviewed_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DroneMissionRoutePreview(DroneMissionBaseModel):
    """GIS-friendly route preview with waypoint markers."""

    mission_id: str
    route_type: DroneMissionRouteType
    waypoints: list[DroneWaypoint]
    estimated_distance_meters: float | None = None
    estimated_duration_seconds: float | None = None
    simulated: bool = True
    operator_review_required: bool = True
    safe_label: str = "Candidate simulated patrol route — not for operational use without review"
    generated_at: str = Field(default_factory=_now_iso)
