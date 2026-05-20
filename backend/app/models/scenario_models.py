from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScenarioState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActorRole(str, Enum):
    SUSPECT = "suspect"
    CIVILIAN = "civilian"
    SECURITY = "security"
    VEHICLE = "vehicle"
    DRONE = "drone"


class ScenarioActor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    actor_id: str
    name: str
    role: ActorRole
    description: str = ""
    camera_ids: list[str] = Field(default_factory=list)
    zone_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step: int
    t_offset_seconds: int
    event_type: str
    description: str
    actor_id: str | None = None
    camera_id: str | None = None
    drone_id: str | None = None
    zone_id: str | None = None
    confidence: float = 0.85
    severity: str = "medium"
    detected_class: str | None = None
    promote_to_alert: bool = False
    promote_to_incident: bool = False
    trigger_drone_dispatch: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    name: str
    description: str
    category: str = "crime"
    camera_ids: list[str] = Field(default_factory=list)
    drone_ids: list[str] = Field(default_factory=list)
    actors: list[ScenarioActor] = Field(default_factory=list)
    timeline: list[ScenarioTimelineEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioRunStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    scenario_id: str
    state: ScenarioState
    mode: str
    current_step: int = 0
    total_steps: int = 0
    started_at: str | None = None
    paused_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    observations_generated: int = 0
    alerts_promoted: int = 0
    incidents_promoted: int = 0
    drone_dispatched: bool = False
    dispatched_drone_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScenarioRun(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    scenario_id: str
    scenario_name: str
    state: ScenarioState
    mode: str
    current_step: int = 0
    total_steps: int = 0
    started_at: str | None = None
    paused_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    observations_generated: int = 0
    alerts_promoted: int = 0
    incidents_promoted: int = 0
    drone_dispatched: bool = False
    dispatched_drone_id: str | None = None
    observation_timeline: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_status(self) -> ScenarioRunStatus:
        return ScenarioRunStatus(
            run_id=self.run_id,
            scenario_id=self.scenario_id,
            state=self.state,
            mode=self.mode,
            current_step=self.current_step,
            total_steps=self.total_steps,
            started_at=self.started_at,
            paused_at=self.paused_at,
            completed_at=self.completed_at,
            cancelled_at=self.cancelled_at,
            observations_generated=self.observations_generated,
            alerts_promoted=self.alerts_promoted,
            incidents_promoted=self.incidents_promoted,
            drone_dispatched=self.drone_dispatched,
            dispatched_drone_id=self.dispatched_drone_id,
            error=self.error,
            metadata=self.metadata,
        )
