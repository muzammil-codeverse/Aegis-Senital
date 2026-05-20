from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CapabilityState(str, Enum):
    REGISTERED = "REGISTERED"
    COLD = "COLD"
    WARMING = "WARMING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    RECOVERING = "RECOVERING"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class CapabilityCategory(str, Enum):
    SYSTEM = "SYSTEM"
    AUTH = "AUTH"
    FRONTEND_API = "FRONTEND_API"
    VIDEO_INTELLIGENCE = "VIDEO_INTELLIGENCE"
    ML_MODEL = "ML_MODEL"
    ML_RUNTIME = "ML_RUNTIME"
    EVENT_INTELLIGENCE = "EVENT_INTELLIGENCE"
    DRONE_SIMULATION = "DRONE_SIMULATION"
    DRONE_MISSION = "DRONE_MISSION"
    DRONE_FUSION = "DRONE_FUSION"
    GIS = "GIS"
    CASE_MANAGEMENT = "CASE_MANAGEMENT"
    EVIDENCE = "EVIDENCE"
    ANALYTICS = "ANALYTICS"
    IDENTITY = "IDENTITY"
    ANOMALY = "ANOMALY"
    OPEN_VOCAB = "OPEN_VOCAB"
    SEGMENTATION = "SEGMENTATION"
    LLM_OSINT = "LLM_OSINT"
    STORAGE = "STORAGE"
    STREAMING = "STREAMING"
    MODEL_GOVERNANCE = "MODEL_GOVERNANCE"


class CapabilityCriticality(str, Enum):
    FOUNDATIONAL = "FOUNDATIONAL"
    MISSION_CORE = "MISSION_CORE"
    MISSION_ADVANCED = "MISSION_ADVANCED"
    SUPPORTING = "SUPPORTING"
    EXTERNAL_DEPENDENT = "EXTERNAL_DEPENDENT"


class CapabilityActivationMode(str, Enum):
    STARTUP = "STARTUP"
    ON_DEMAND = "ON_DEMAND"
    PREFLIGHT = "PREFLIGHT"
    JOB_TRIGGERED = "JOB_TRIGGERED"
    EXTERNAL_TRIGGERED = "EXTERNAL_TRIGGERED"
    MANUAL = "MANUAL"


class CapabilityResourceProfile(str, Enum):
    CPU_LIGHT = "CPU_LIGHT"
    CPU_HEAVY = "CPU_HEAVY"
    GPU_LIGHT = "GPU_LIGHT"
    GPU_HEAVY = "GPU_HEAVY"
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"
    FILE_IO = "FILE_IO"
    NETWORK_IO = "NETWORK_IO"


class CapabilityDescriptor(BaseModel):
    id: str
    name: str
    category: CapabilityCategory
    criticality: CapabilityCriticality
    activation_mode: CapabilityActivationMode
    dependencies: list[str] = Field(default_factory=list)
    description: str = ""
    owner: str | None = None
    resource_profile: list[CapabilityResourceProfile] = Field(default_factory=list)
    config_key: str | None = None
    component_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityRuntimeStatus(BaseModel):
    capability_id: str
    state: CapabilityState = CapabilityState.REGISTERED
    state_reason: str = "Capability registered."
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error: str | None = None
    health_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityRecord(BaseModel):
    descriptor: CapabilityDescriptor
    runtime_status: CapabilityRuntimeStatus

    def to_api_dict(self) -> dict[str, Any]:
        descriptor = self.descriptor.model_dump(mode="json")
        runtime_status = self.runtime_status.model_dump(mode="json")
        return {
            **descriptor,
            "state": runtime_status["state"],
            "state_reason": runtime_status["state_reason"],
            "last_checked_at": runtime_status["last_checked_at"],
            "last_success_at": runtime_status["last_success_at"],
            "last_error_at": runtime_status["last_error_at"],
            "last_error": runtime_status["last_error"],
            "health_score": runtime_status["health_score"],
            "runtime_metadata": runtime_status["metadata"],
            "descriptor": descriptor,
            "runtime_status": runtime_status,
        }
