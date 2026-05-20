from __future__ import annotations

import threading
from typing import Any

from app.core.capabilities.lifecycle import is_success_state, normalize_state, utc_now_iso
from app.core.capabilities.models import (
    CapabilityDescriptor,
    CapabilityRecord,
    CapabilityRuntimeStatus,
    CapabilityState,
)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, CapabilityRecord] = {}

    def register(self, descriptor: CapabilityDescriptor) -> CapabilityRecord:
        with self._lock:
            existing = self._records.get(descriptor.id)
            if existing is not None:
                existing.descriptor = descriptor
                return existing
            record = CapabilityRecord(
                descriptor=descriptor,
                runtime_status=CapabilityRuntimeStatus(capability_id=descriptor.id),
            )
            self._records[descriptor.id] = record
            return record

    def get(self, capability_id: str) -> CapabilityRecord:
        with self._lock:
            try:
                return self._records[capability_id]
            except KeyError as exc:
                raise KeyError(f"Capability '{capability_id}' is not registered") from exc

    def get_or_none(self, capability_id: str) -> CapabilityRecord | None:
        with self._lock:
            return self._records.get(capability_id)

    def list(self) -> list[CapabilityRecord]:
        with self._lock:
            return list(self._records.values())

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def update_status(
        self,
        capability_id: str,
        state: CapabilityState | str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        *,
        health_score: float | None = None,
    ) -> CapabilityRecord:
        normalized_state = normalize_state(state)
        with self._lock:
            record = self.get(capability_id)
            status = record.runtime_status
            now = utc_now_iso()
            status.state = normalized_state
            status.state_reason = reason
            status.last_checked_at = now
            if is_success_state(normalized_state):
                status.last_success_at = now
                status.last_error = None
                status.last_error_at = None
            if normalized_state == CapabilityState.FAULTED:
                status.last_error_at = now
            if metadata:
                status.metadata.update(metadata)
            if health_score is not None:
                status.health_score = max(0.0, min(1.0, float(health_score)))
            return record

    def mark_faulted(
        self,
        capability_id: str,
        error: Exception | str,
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityRecord:
        message = str(error)[:500]
        with self._lock:
            record = self.get(capability_id)
            status = record.runtime_status
            now = utc_now_iso()
            status.state = CapabilityState.FAULTED
            status.state_reason = "Capability faulted."
            status.last_checked_at = now
            status.last_error_at = now
            status.last_error = message
            status.health_score = 0.0
            if metadata:
                status.metadata.update(metadata)
            return record

    def mark_degraded(
        self,
        capability_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityRecord:
        return self.update_status(
            capability_id,
            CapabilityState.DEGRADED,
            reason,
            metadata,
            health_score=0.45,
        )

    def mark_ready(
        self,
        capability_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityRecord:
        return self.update_status(
            capability_id,
            CapabilityState.READY,
            reason,
            metadata,
            health_score=1.0,
        )

    def dependency_overview(self) -> dict[str, Any]:
        with self._lock:
            ids = set(self._records)
            dependents: dict[str, list[str]] = {capability_id: [] for capability_id in ids}
            overview: dict[str, Any] = {}
            for capability_id, record in self._records.items():
                dependencies = list(record.descriptor.dependencies)
                for dependency in dependencies:
                    dependents.setdefault(dependency, []).append(capability_id)
                overview[capability_id] = {
                    "dependencies": dependencies,
                    "missing_dependencies": [dependency for dependency in dependencies if dependency not in ids],
                    "dependents": [],
                }
            for capability_id, linked in dependents.items():
                overview.setdefault(
                    capability_id,
                    {"dependencies": [], "missing_dependencies": [], "dependents": []},
                )
                overview[capability_id]["dependents"] = sorted(linked)
            return overview

    def to_api_list(self) -> list[dict[str, Any]]:
        return [record.to_api_dict() for record in self.list()]


_registry: CapabilityRegistry | None = None
_registry_lock = threading.Lock()


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CapabilityRegistry()
    return _registry
