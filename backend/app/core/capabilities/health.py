from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from app.core.capabilities.lifecycle import utc_now_iso
from app.core.capabilities.models import (
    CapabilityCriticality,
    CapabilityRecord,
    CapabilityResourceProfile,
    CapabilityState,
)
from app.core.capabilities.registry import CapabilityRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _state_counts(records: list[CapabilityRecord]) -> dict[str, int]:
    counts = Counter(record.runtime_status.state.value for record in records)
    for state in CapabilityState:
        counts.setdefault(state.value, 0)
    return dict(counts)


def _rollup_state(records: list[CapabilityRecord]) -> str:
    if not records:
        return CapabilityState.UNKNOWN.value
    states = {record.runtime_status.state for record in records}
    if CapabilityState.FAULTED in states:
        return CapabilityState.FAULTED.value
    if CapabilityState.RECOVERING in states:
        return CapabilityState.RECOVERING.value
    if CapabilityState.DEGRADED in states:
        return CapabilityState.DEGRADED.value
    if CapabilityState.ACTIVE in states:
        return CapabilityState.ACTIVE.value
    if states <= {CapabilityState.READY, CapabilityState.DISABLED}:
        return CapabilityState.READY.value
    if CapabilityState.WARMING in states:
        return CapabilityState.WARMING.value
    if CapabilityState.COLD in states or CapabilityState.REGISTERED in states:
        return CapabilityState.COLD.value
    return CapabilityState.UNKNOWN.value


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def _nested_get(payload: dict[str, Any], dotted_key: str | None) -> Any:
    if not dotted_key:
        return None
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _resolve_repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _configured_disabled(record: CapabilityRecord) -> bool:
    config_path = _resolve_repo_path(record.descriptor.metadata.get("config_path"))
    enabled_path = record.descriptor.metadata.get("enabled_path")
    if config_path is None or not enabled_path:
        return False
    payload = _read_yaml(config_path)
    enabled_value = _nested_get(payload, str(enabled_path))
    return enabled_value is False


def _missing_required_paths(record: CapabilityRecord) -> list[str]:
    missing: list[str] = []
    for raw in record.descriptor.metadata.get("required_paths") or []:
        path = _resolve_repo_path(str(raw))
        if path is not None and not path.exists():
            missing.append(str(path))
    return missing


def _check_local_storage(registry: CapabilityRegistry, record: CapabilityRecord) -> CapabilityRecord:
    paths = record.descriptor.metadata.get("writable_paths") or ["storage", "runtime_state", "logs"]
    checked: list[str] = []
    for raw in paths:
        path = _resolve_repo_path(str(raw))
        if path is None:
            continue
        path.mkdir(parents=True, exist_ok=True)
        checked.append(str(path))
        if not os.access(str(path), os.W_OK):
            return registry.mark_faulted(record.descriptor.id, f"Storage path is not writable: {path}")
    return registry.mark_ready(
        record.descriptor.id,
        "Local-first storage paths are present and writable.",
        {"checked_paths": checked},
    )


def refresh_capability_status(registry: CapabilityRegistry, capability_id: str) -> CapabilityRecord:
    record = registry.get(capability_id)
    descriptor = record.descriptor
    current_state = record.runtime_status.state

    if descriptor.id == "local_storage":
        return _check_local_storage(registry, record)

    if descriptor.activation_mode.value == "STARTUP" and descriptor.criticality == CapabilityCriticality.FOUNDATIONAL:
        return registry.mark_ready(
            descriptor.id,
            "Foundational capability passed lightweight startup readiness check.",
        )

    try:
        if _configured_disabled(record):
            return registry.update_status(
                descriptor.id,
                CapabilityState.DISABLED,
                "Capability is intentionally disabled by runtime configuration.",
                health_score=0.0,
            )
    except FileNotFoundError as exc:
        return registry.mark_degraded(
            descriptor.id,
            f"Runtime configuration is missing: {exc}",
        )
    except Exception as exc:
        return registry.mark_degraded(
            descriptor.id,
            f"Runtime configuration could not be checked: {str(exc)[:160]}",
        )

    missing = _missing_required_paths(record)
    if missing:
        return registry.mark_degraded(
            descriptor.id,
            "Capability is registered but one or more lightweight assets/config paths are missing.",
            {"missing_paths": missing},
        )

    env_vars = [str(item) for item in (descriptor.metadata.get("required_env") or [])]
    missing_env = [name for name in env_vars if not os.getenv(name, "").strip()]
    if missing_env:
        return registry.mark_degraded(
            descriptor.id,
            "External dependency configuration is incomplete; capability remains registered for managed activation.",
            {"missing_env": missing_env},
        )

    if CapabilityResourceProfile.EXTERNAL_SERVICE in descriptor.resource_profile:
        return registry.update_status(
            descriptor.id,
            CapabilityState.COLD,
            "External service capability is registered; provider connection is awaiting managed activation.",
            health_score=0.65,
        )

    if current_state in {CapabilityState.READY, CapabilityState.ACTIVE, CapabilityState.WARMING}:
        return registry.update_status(
            descriptor.id,
            current_state,
            record.runtime_status.state_reason,
            health_score=record.runtime_status.health_score,
        )

    return registry.update_status(
        descriptor.id,
        CapabilityState.COLD,
        "Capability is registered and awaiting warmup, preflight, or job-triggered activation.",
        health_score=0.7,
    )


def refresh_all_capability_statuses(registry: CapabilityRegistry) -> list[CapabilityRecord]:
    refreshed: list[CapabilityRecord] = []
    for record in registry.list():
        refreshed.append(refresh_capability_status(registry, record.descriptor.id))
    return refreshed


def aggregate_capability_health(records: list[CapabilityRecord]) -> dict[str, Any]:
    foundational = [r for r in records if r.descriptor.criticality == CapabilityCriticality.FOUNDATIONAL]
    mission_core = [r for r in records if r.descriptor.criticality == CapabilityCriticality.MISSION_CORE]
    mission_advanced = [r for r in records if r.descriptor.criticality == CapabilityCriticality.MISSION_ADVANCED]

    by_state = _state_counts(records)
    by_category: dict[str, dict[str, int]] = {}
    for record in records:
        category = record.descriptor.category.value
        by_category.setdefault(category, _state_counts([]))
        by_category[category][record.runtime_status.state.value] += 1

    def ids_for(*states: CapabilityState) -> list[str]:
        wanted = set(states)
        return sorted(record.descriptor.id for record in records if record.runtime_status.state in wanted)

    def group_payload(group_records: list[CapabilityRecord]) -> dict[str, Any]:
        return {
            "state": _rollup_state(group_records),
            "total": len(group_records),
            "counts": _state_counts(group_records),
            "faulted": ids_for_in_group(group_records, CapabilityState.FAULTED),
            "degraded": ids_for_in_group(group_records, CapabilityState.DEGRADED),
            "cold": ids_for_in_group(group_records, CapabilityState.COLD, CapabilityState.REGISTERED),
            "ready": ids_for_in_group(group_records, CapabilityState.READY, CapabilityState.ACTIVE),
        }

    def ids_for_in_group(group_records: list[CapabilityRecord], *states: CapabilityState) -> list[str]:
        wanted = set(states)
        return sorted(record.descriptor.id for record in group_records if record.runtime_status.state in wanted)

    return {
        "generated_at": utc_now_iso(),
        "overall_state": _rollup_state(records),
        "total": len(records),
        "by_state": by_state,
        "by_category": by_category,
        "ready": by_state[CapabilityState.READY.value],
        "cold": by_state[CapabilityState.COLD.value] + by_state[CapabilityState.REGISTERED.value],
        "degraded": by_state[CapabilityState.DEGRADED.value],
        "faulted": by_state[CapabilityState.FAULTED.value],
        "active": by_state[CapabilityState.ACTIVE.value],
        "warming": by_state[CapabilityState.WARMING.value],
        "recovering": by_state[CapabilityState.RECOVERING.value],
        "disabled": by_state[CapabilityState.DISABLED.value],
        "unknown": by_state[CapabilityState.UNKNOWN.value],
        "foundational_status": group_payload(foundational),
        "mission_core_status": group_payload(mission_core),
        "mission_advanced_status": group_payload(mission_advanced),
        "degraded_capabilities": ids_for(CapabilityState.DEGRADED),
        "faulted_capabilities": ids_for(CapabilityState.FAULTED),
        "cold_capabilities": ids_for(CapabilityState.COLD, CapabilityState.REGISTERED),
        "ready_capabilities": ids_for(CapabilityState.READY),
        "active_capabilities": ids_for(CapabilityState.ACTIVE),
    }
