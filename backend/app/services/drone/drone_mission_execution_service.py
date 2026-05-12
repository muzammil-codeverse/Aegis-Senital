"""Mission execution service for simulated drone patrol missions (Phase 45).

Drives mission execution against the Cosys-AirSim simulator.
Gracefully handles simulator disconnection — never generates fake telemetry.
All missions are simulated-only; no real-world deployment is implied.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.models.drone_mission_models import (
    DroneMissionEvent,
    DroneMissionEventType,
    DroneMissionPlan,
    DroneMissionReport,
    DroneMissionSession,
    DroneMissionStatus,
    DroneMissionTelemetryPoint,
)
from app.repositories.drone_mission_repository import (
    DroneMissionRepository,
    get_drone_mission_repository,
)
from app.services.drone.drone_coordinate_mapper import (
    NEDPoint,
    geo_to_ned,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(started_at: str | None, completed_at: str | None) -> float | None:
    """Return the duration in seconds between two ISO timestamps, or None."""
    if not started_at or not completed_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
        return (end - start).total_seconds()
    except Exception:
        return None


class MissionExecutionError(Exception):
    """Raised when mission execution cannot proceed."""


class DroneMissionExecutionService:
    """Executes a simulated drone patrol mission via Cosys-AirSim.

    On simulator disconnection the mission is immediately transitioned to
    'failed' status and a SIMULATOR_DISCONNECTED event is recorded.
    No fake telemetry is ever generated.
    """

    def __init__(
        self,
        repository: DroneMissionRepository | None = None,
    ) -> None:
        self._repo = repository or get_drone_mission_repository()

    # ------------------------------------------------------------------
    # Simulator connectivity helper
    # ------------------------------------------------------------------

    def _get_airsim_client(self) -> Any | None:
        """Return an initialised Cosys-AirSim client, or None if unavailable."""
        try:
            from app.services.drone.cosys_airsim_client import (
                CosysAirSimClient,
                get_cosys_airsim_client,
            )
            client = get_cosys_airsim_client()
            if client.is_connected():
                return client
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_mission(
        self,
        mission: DroneMissionPlan,
        session: DroneMissionSession,
        started_by: str | None = None,
    ) -> DroneMissionSession:
        """Start executing a simulated patrol mission.

        If the simulator is not connected the session is immediately
        transitioned to 'failed' and an event is recorded.
        """
        client = self._get_airsim_client()
        if client is None:
            # Graceful failure — no fake telemetry
            now = _now_iso()
            self._repo.update_session(
                session.session_id,
                {
                    "status": DroneMissionStatus.FAILED.value,
                    "last_error": "Simulator not connected — mission cannot be started",
                    "updated_at": now,
                },
            )
            self._record_event(
                session,
                DroneMissionEventType.SIMULATOR_DISCONNECTED,
                detail="Cosys-AirSim simulator is not connected; mission blocked",
            )
            self._record_event(
                session,
                DroneMissionEventType.MISSION_FAILED,
                detail="Mission failed: simulator unavailable",
            )
            updated = self._repo.get_session(session.session_id)
            return updated or session

        # Simulator is connected — start the mission
        now = _now_iso()
        self._repo.update_session(
            session.session_id,
            {
                "status": DroneMissionStatus.EXECUTING.value,
                "started_at": now,
                "started_by": started_by,
                "total_waypoints": len(mission.waypoints),
                "updated_at": now,
            },
        )
        self._repo.update_mission(
            mission.mission_id,
            {"status": DroneMissionStatus.EXECUTING.value, "updated_at": now},
        )
        self._record_event(
            session,
            DroneMissionEventType.MISSION_STARTED,
            detail="Simulated aerial patrol mission started",
        )
        updated = self._repo.get_session(session.session_id)
        return updated or session

    def pause_mission(self, session_id: str) -> DroneMissionSession | None:
        """Pause an executing simulated mission."""
        session = self._repo.get_session(session_id)
        if session is None:
            return None
        if session.status != DroneMissionStatus.EXECUTING:
            raise MissionExecutionError(
                f"Cannot pause mission in status '{session.status.value}'"
            )
        now = _now_iso()
        self._repo.update_session(
            session_id,
            {"status": DroneMissionStatus.PAUSED.value, "paused_at": now, "updated_at": now},
        )
        self._record_event(session, DroneMissionEventType.MISSION_PAUSED, detail="Simulated patrol paused by operator")
        return self._repo.get_session(session_id)

    def resume_mission(self, session_id: str) -> DroneMissionSession | None:
        """Resume a paused simulated mission."""
        session = self._repo.get_session(session_id)
        if session is None:
            return None
        if session.status != DroneMissionStatus.PAUSED:
            raise MissionExecutionError(
                f"Cannot resume mission in status '{session.status.value}'"
            )
        client = self._get_airsim_client()
        if client is None:
            now = _now_iso()
            self._repo.update_session(
                session_id,
                {
                    "status": DroneMissionStatus.FAILED.value,
                    "last_error": "Simulator not connected — cannot resume",
                    "updated_at": now,
                },
            )
            self._record_event(session, DroneMissionEventType.SIMULATOR_DISCONNECTED)
            return self._repo.get_session(session_id)

        now = _now_iso()
        self._repo.update_session(
            session_id,
            {"status": DroneMissionStatus.EXECUTING.value, "resumed_at": now, "updated_at": now},
        )
        self._record_event(session, DroneMissionEventType.MISSION_RESUMED, detail="Simulated patrol resumed")
        return self._repo.get_session(session_id)

    def cancel_mission(self, session_id: str, reason: str | None = None) -> DroneMissionSession | None:
        """Cancel a mission session."""
        session = self._repo.get_session(session_id)
        if session is None:
            return None
        if session.status in (DroneMissionStatus.COMPLETED, DroneMissionStatus.CANCELLED):
            raise MissionExecutionError(
                f"Mission is already in terminal status '{session.status.value}'"
            )
        now = _now_iso()
        self._repo.update_session(
            session_id,
            {
                "status": DroneMissionStatus.CANCELLED.value,
                "completed_at": now,
                "updated_at": now,
            },
        )
        self._repo.update_mission(
            session.mission_id,
            {"status": DroneMissionStatus.CANCELLED.value, "updated_at": now},
        )
        self._record_event(
            session,
            DroneMissionEventType.MISSION_CANCELLED,
            detail=reason or "Mission cancelled by operator",
        )
        return self._repo.get_session(session_id)

    def get_mission_status(self, session_id: str) -> dict[str, Any]:
        """Return current status and progress of a mission session."""
        session = self._repo.get_session(session_id)
        if session is None:
            return {"status": "not_found", "session_id": session_id}
        return {
            "session_id": session.session_id,
            "mission_id": session.mission_id,
            "status": session.status.value,
            "current_waypoint_index": session.current_waypoint_index,
            "progress_percent": session.progress_percent,
            "total_waypoints": session.total_waypoints,
            "waypoints_reached": session.waypoints_reached,
            "telemetry_count": session.telemetry_count,
            "event_count": session.event_count,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "last_error": session.last_error,
            "simulated": True,
            "operator_review_required": True,
            "checked_at": _now_iso(),
        }

    def record_telemetry(self, point: DroneMissionTelemetryPoint) -> None:
        """Persist a telemetry point and update session counter."""
        self._repo.append_telemetry(point)
        session = self._repo.get_session(point.session_id)
        if session is not None:
            self._repo.update_session(
                point.session_id,
                {"telemetry_count": session.telemetry_count + 1, "updated_at": _now_iso()},
            )

    def complete_mission(self, session: DroneMissionSession) -> DroneMissionSession | None:
        """Mark a session as completed and generate a report."""
        now = _now_iso()
        self._repo.update_session(
            session.session_id,
            {
                "status": DroneMissionStatus.COMPLETED.value,
                "completed_at": now,
                "progress_percent": 100.0,
                "updated_at": now,
            },
        )
        self._repo.update_mission(
            session.mission_id,
            {"status": DroneMissionStatus.COMPLETED.value, "updated_at": now},
        )
        self._record_event(session, DroneMissionEventType.MISSION_COMPLETED, detail="Simulated aerial patrol completed")
        updated = self._repo.get_session(session.session_id)
        if updated:
            self._generate_and_save_report(updated)
        return updated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_event(
        self,
        session: DroneMissionSession,
        event_type: DroneMissionEventType,
        *,
        waypoint_index: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_meters: float | None = None,
        detail: str | None = None,
    ) -> None:
        """Create and persist a mission event, then update session counter."""
        event = DroneMissionEvent(
            session_id=session.session_id,
            mission_id=session.mission_id,
            drone_id=session.drone_id,
            event_type=event_type,
            waypoint_index=waypoint_index,
            latitude=latitude,
            longitude=longitude,
            altitude_meters=altitude_meters,
            detail=detail,
        )
        self._repo.append_event(event)
        # Update the event counter on the session
        stored = self._repo.get_session(session.session_id)
        count = (stored.event_count if stored else session.event_count) + 1
        self._repo.update_session(
            session.session_id,
            {"event_count": count, "updated_at": _now_iso()},
        )

    def _generate_and_save_report(self, session: DroneMissionSession) -> DroneMissionReport:
        """Generate and persist a post-mission report."""
        duration = _duration(session.started_at, session.completed_at)
        completion = (
            (session.waypoints_reached / max(session.total_waypoints, 1)) * 100.0
            if session.total_waypoints > 0
            else 0.0
        )
        report = DroneMissionReport(
            session_id=session.session_id,
            mission_id=session.mission_id,
            drone_id=session.drone_id,
            mission_status=session.status,
            total_waypoints=session.total_waypoints,
            waypoints_reached=session.waypoints_reached,
            completion_percent=round(completion, 2),
            started_at=session.started_at,
            completed_at=session.completed_at,
            duration_seconds=duration,
            telemetry_count=session.telemetry_count,
            event_count=session.event_count,
        )
        return self._repo.save_report(report)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_exec_service: DroneMissionExecutionService | None = None
_exec_lock = threading.Lock()


def get_drone_mission_execution_service() -> DroneMissionExecutionService:
    """Return the process-wide DroneMissionExecutionService singleton."""
    global _exec_service
    if _exec_service is None:
        with _exec_lock:
            if _exec_service is None:
                _exec_service = DroneMissionExecutionService()
    return _exec_service
