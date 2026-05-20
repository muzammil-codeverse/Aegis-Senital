from __future__ import annotations

from datetime import datetime, timezone

from app.core.capabilities.models import CapabilityState


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_success_state(state: CapabilityState | str) -> bool:
    normalized = CapabilityState(state)
    return normalized in {CapabilityState.READY, CapabilityState.ACTIVE}


def is_failure_state(state: CapabilityState | str) -> bool:
    normalized = CapabilityState(state)
    return normalized in {CapabilityState.FAULTED, CapabilityState.DEGRADED}


def normalize_state(value: CapabilityState | str) -> CapabilityState:
    if isinstance(value, CapabilityState):
        return value
    return CapabilityState(str(value).upper())
