from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.capabilities.models import CapabilityState


class PreflightMode(str, Enum):
    QUICK = "QUICK"
    EXHIBITION = "EXHIBITION"
    DEEP = "DEEP"


class PreflightRunStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    PARTIALLY_PASSED = "PARTIALLY_PASSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PreflightCapabilityGroup(str, Enum):
    FOUNDATIONAL = "FOUNDATIONAL"
    COMMAND_CENTER = "COMMAND_CENTER"
    VIDEO_INTELLIGENCE = "VIDEO_INTELLIGENCE"
    DRONE_SYSTEM = "DRONE_SYSTEM"
    ADVANCED_INTELLIGENCE = "ADVANCED_INTELLIGENCE"


class PreflightCheckStatus(str, Enum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PreflightRecommendation(BaseModel):
    severity: str = "info"
    capability_id: str | None = None
    message: str
    action: str | None = None


class PreflightCheckResult(BaseModel):
    level: int
    name: str
    status: PreflightCheckStatus
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PreflightCapabilityResult(BaseModel):
    capability_id: str
    name: str
    group: PreflightCapabilityGroup
    state: CapabilityState
    check_level: int = 1
    checks: list[PreflightCheckResult] = Field(default_factory=list)
    blocking: bool = False
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    registry_state_after_check: CapabilityState | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PreflightRun(BaseModel):
    run_id: str
    started_at: str
    completed_at: str | None = None
    triggered_by: str | None = None
    mode: PreflightMode
    selected_capabilities: list[str] = Field(default_factory=list)
    results: list[PreflightCapabilityResult] = Field(default_factory=list)
    overall_status: PreflightRunStatus = PreflightRunStatus.RUNNING
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[PreflightRecommendation] = Field(default_factory=list)
    duration_ms: int = 0


class PreflightSummary(BaseModel):
    generated_at: str
    latest_run_id: str | None = None
    overall_status: PreflightRunStatus = PreflightRunStatus.NOT_STARTED
    mode: PreflightMode | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int = 0
    total: int = 0
    by_state: dict[str, int] = Field(default_factory=dict)
    groups: dict[str, dict[str, Any]] = Field(default_factory=dict)
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[PreflightRecommendation] = Field(default_factory=list)


class PreflightRunRequest(BaseModel):
    mode: PreflightMode = PreflightMode.QUICK
    selected_capabilities: list[str] | None = None

