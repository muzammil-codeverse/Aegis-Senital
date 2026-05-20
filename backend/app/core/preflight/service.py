from __future__ import annotations

import threading
import time
import uuid
from collections import Counter

from app.core.capabilities.defaults import register_default_capabilities
from app.core.capabilities.lifecycle import utc_now_iso
from app.core.capabilities.models import CapabilityState
from app.core.capabilities.registry import CapabilityRegistry, get_capability_registry
from app.core.preflight.checks import capabilities_for_mode, evaluate_capability, grouped_state_counts
from app.core.preflight.models import (
    PreflightCapabilityResult,
    PreflightMode,
    PreflightRecommendation,
    PreflightRun,
    PreflightRunStatus,
    PreflightSummary,
)


class PreflightService:
    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry or get_capability_registry()
        self._lock = threading.RLock()
        self._runs: dict[str, PreflightRun] = {}
        self._latest_run_id: str | None = None

    @property
    def registry(self) -> CapabilityRegistry:
        register_default_capabilities(self._registry)
        return self._registry

    def start_preflight(
        self,
        mode: PreflightMode | str = PreflightMode.QUICK,
        selected_capabilities: list[str] | None = None,
        triggered_by: str | None = None,
    ) -> PreflightRun:
        preflight_mode = mode if isinstance(mode, PreflightMode) else PreflightMode(str(mode).upper())
        capability_ids = selected_capabilities or capabilities_for_mode(preflight_mode)
        run = PreflightRun(
            run_id=str(uuid.uuid4()),
            started_at=utc_now_iso(),
            triggered_by=triggered_by,
            mode=preflight_mode,
            selected_capabilities=list(capability_ids),
            overall_status=PreflightRunStatus.RUNNING,
        )
        with self._lock:
            self._runs[run.run_id] = run
            self._latest_run_id = run.run_id
        return self.run_preflight_sync(run.run_id)

    def run_preflight_sync(self, run_id: str) -> PreflightRun:
        start = time.perf_counter()
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(f"Preflight run '{run_id}' not found")
            run = self._runs[run_id]
            run.overall_status = PreflightRunStatus.RUNNING

        try:
            results = [
                self.evaluate_capability(capability_id, run.mode)
                for capability_id in run.selected_capabilities
            ]
            run.results = results
            run.blocking_failures = self._blocking_failures(results)
            run.warnings = self._warnings(results, run.mode)
            run.recommendations = self._recommendations(results, run.mode)
            run.overall_status = self._overall_status(run)
        except Exception as exc:
            run.blocking_failures = [str(exc)[:240]]
            run.warnings = []
            run.recommendations = [
                PreflightRecommendation(
                    severity="critical",
                    message="Preflight system failed before completing all checks.",
                    action="Review backend logs and rerun QUICK preflight after resolving the exception.",
                )
            ]
            run.overall_status = PreflightRunStatus.FAILED
        finally:
            run.completed_at = utc_now_iso()
            run.duration_ms = int((time.perf_counter() - start) * 1000)
            with self._lock:
                self._runs[run.run_id] = run
                self._latest_run_id = run.run_id
        return run

    def evaluate_capability(
        self,
        capability_id: str,
        mode: PreflightMode | str = PreflightMode.EXHIBITION,
    ) -> PreflightCapabilityResult:
        preflight_mode = mode if isinstance(mode, PreflightMode) else PreflightMode(str(mode).upper())
        result = evaluate_capability(self.registry, capability_id, preflight_mode)
        self.update_capability_registry_from_preflight(result)
        return result

    def get_latest_preflight(self) -> PreflightRun:
        with self._lock:
            if not self._latest_run_id:
                return self._not_started_run()
            return self._runs[self._latest_run_id]

    def get_preflight_run(self, run_id: str) -> PreflightRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise KeyError(f"Preflight run '{run_id}' not found") from exc

    def summarize_preflight_results(self, run: PreflightRun | None = None) -> PreflightSummary:
        latest = run or self.get_latest_preflight()
        results = latest.results
        counts = Counter(result.state.value for result in results)
        for state in CapabilityState:
            counts.setdefault(state.value, 0)
        return PreflightSummary(
            generated_at=utc_now_iso(),
            latest_run_id=None if latest.overall_status == PreflightRunStatus.NOT_STARTED else latest.run_id,
            overall_status=latest.overall_status,
            mode=latest.mode,
            started_at=latest.started_at,
            completed_at=latest.completed_at,
            duration_ms=latest.duration_ms,
            total=len(results),
            by_state=dict(counts),
            groups=grouped_state_counts(results),
            blocking_failures=latest.blocking_failures,
            warnings=latest.warnings,
            recommendations=latest.recommendations,
        )

    def update_capability_registry_from_preflight(self, result: PreflightCapabilityResult) -> None:
        metadata = {
            "preflight": {
                "mode": result.metadata.get("mode"),
                "group": result.group.value,
                "check_level": result.check_level,
                "warnings": result.warnings,
                "recommendations": result.recommendations,
            }
        }
        for key in ("provider", "openai_key_present", "openai_key_masked", "configured_disabled"):
            if key in result.metadata:
                metadata["preflight"][key] = result.metadata[key]

        if result.state == CapabilityState.READY:
            record = self.registry.mark_ready(result.capability_id, result.reason, metadata)
        elif result.state == CapabilityState.DEGRADED:
            record = self.registry.mark_degraded(result.capability_id, result.reason, metadata)
        elif result.state == CapabilityState.FAULTED:
            record = self.registry.mark_faulted(result.capability_id, result.reason, metadata)
        else:
            record = self.registry.update_status(
                result.capability_id,
                result.state,
                result.reason,
                metadata,
                health_score=self._health_score_for_state(result.state),
            )
        result.registry_state_after_check = record.runtime_status.state

    def _overall_status(self, run: PreflightRun) -> PreflightRunStatus:
        if run.blocking_failures:
            return PreflightRunStatus.FAILED
        if run.mode == PreflightMode.DEEP:
            return PreflightRunStatus.PARTIALLY_PASSED
        if run.mode == PreflightMode.QUICK:
            if any(result.state in {CapabilityState.FAULTED, CapabilityState.DEGRADED, CapabilityState.UNKNOWN} for result in run.results):
                return PreflightRunStatus.PARTIALLY_PASSED
            return PreflightRunStatus.PASSED
        if any(result.state not in {CapabilityState.READY, CapabilityState.ACTIVE} for result in run.results):
            return PreflightRunStatus.PARTIALLY_PASSED
        return PreflightRunStatus.PASSED

    @staticmethod
    def _blocking_failures(results: list[PreflightCapabilityResult]) -> list[str]:
        failures: list[str] = []
        for result in results:
            if result.blocking and result.state in {CapabilityState.FAULTED, CapabilityState.DEGRADED, CapabilityState.UNKNOWN}:
                failures.append(f"{result.capability_id}: {result.reason}")
        return failures

    @staticmethod
    def _warnings(results: list[PreflightCapabilityResult], mode: PreflightMode) -> list[str]:
        warnings: list[str] = []
        if mode == PreflightMode.DEEP:
            warnings.append("DEEP preflight mode is registered in Phase 2 but heavy warmup remains deferred.")
        for result in results:
            for warning in result.warnings:
                warnings.append(f"{result.capability_id}: {warning}")
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _recommendations(results: list[PreflightCapabilityResult], mode: PreflightMode) -> list[PreflightRecommendation]:
        recommendations: list[PreflightRecommendation] = []
        if mode == PreflightMode.DEEP:
            recommendations.append(
                PreflightRecommendation(
                    severity="warning",
                    message="DEEP mode is a Phase 2 placeholder.",
                    action="Use EXHIBITION preflight for safe local demo readiness; defer heavy GPU sequencing to Phase 5.",
                )
            )
        for result in results:
            severity = "info"
            if result.state == CapabilityState.DEGRADED:
                severity = "warning"
            elif result.state == CapabilityState.FAULTED:
                severity = "critical"
            for message in result.recommendations:
                recommendations.append(
                    PreflightRecommendation(
                        severity=severity,
                        capability_id=result.capability_id,
                        message=message,
                    )
                )
        deduped: list[PreflightRecommendation] = []
        seen: set[tuple[str | None, str]] = set()
        for item in recommendations:
            key = (item.capability_id, item.message)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _health_score_for_state(state: CapabilityState) -> float:
        if state in {CapabilityState.READY, CapabilityState.ACTIVE}:
            return 1.0
        if state in {CapabilityState.COLD, CapabilityState.REGISTERED}:
            return 0.7
        if state == CapabilityState.DEGRADED:
            return 0.45
        if state == CapabilityState.DISABLED:
            return 0.2
        if state == CapabilityState.WARMING:
            return 0.75
        return 0.0

    @staticmethod
    def _not_started_run() -> PreflightRun:
        return PreflightRun(
            run_id="not-started",
            started_at=utc_now_iso(),
            mode=PreflightMode.QUICK,
            overall_status=PreflightRunStatus.NOT_STARTED,
        )


_preflight_service: PreflightService | None = None
_preflight_lock = threading.Lock()


def get_preflight_service(registry: CapabilityRegistry | None = None) -> PreflightService:
    global _preflight_service
    if registry is not None:
        return PreflightService(registry)
    if _preflight_service is None:
        with _preflight_lock:
            if _preflight_service is None:
                _preflight_service = PreflightService()
    return _preflight_service

