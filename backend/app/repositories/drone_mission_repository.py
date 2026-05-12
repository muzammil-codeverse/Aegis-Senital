"""JSONL-based repository for drone patrol mission data (Phase 45).

Provides a PostgreSQL-ready abstraction backed by JSONL files for development.
All stored artifacts carry simulated=True; no real-world data is persisted here.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.drone_mission_models import (
    DroneMissionEvent,
    DroneMissionPlan,
    DroneMissionReport,
    DroneMissionSession,
    DroneMissionStatus,
    DroneMissionTelemetryPoint,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class DroneMissionRepository:
    """JSONL dev storage for drone patrol mission artifacts.

    Each entity type is stored in a dedicated .jsonl file.  The interface
    mirrors what a PostgreSQL-backed production repository would expose so
    that swapping the implementation does not require API changes.
    """

    def __init__(self, root_dir: str | Path | None = None) -> None:
        root = Path(root_dir) if root_dir else Path("storage/drone_missions")
        root.mkdir(parents=True, exist_ok=True)
        (root / "telemetry").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)

        self._missions_path = root / "missions.jsonl"
        self._sessions_path = root / "sessions.jsonl"
        self._telemetry_path = root / "telemetry" / "telemetry.jsonl"
        self._events_path = root / "events.jsonl"
        self._reports_path = root / "reports" / "reports.jsonl"

        self._lock = threading.Lock()
        self.storage_backend = "jsonl"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self, path: Path) -> list[dict[str, Any]]:
        """Read all JSONL records from *path*."""
        if not path.exists():
            return []
        results: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return results

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        """Append *record* as a single JSON line to *path*."""
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _rewrite(self, path: Path, records: list[dict[str, Any]]) -> None:
        """Overwrite *path* with the supplied list of records."""
        with path.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------
    # Mission CRUD
    # ------------------------------------------------------------------

    def create_mission(self, mission: DroneMissionPlan) -> DroneMissionPlan:
        """Persist a new mission plan and return it."""
        with self._lock:
            self._append(self._missions_path, mission.model_dump(mode="json"))
        return mission

    def update_mission(self, mission_id: str, updates: dict[str, Any]) -> DroneMissionPlan | None:
        """Apply *updates* to the mission identified by *mission_id*."""
        with self._lock:
            records = self._read_all(self._missions_path)
            updated = None
            for rec in records:
                if rec.get("mission_id") == mission_id:
                    rec.update(updates)
                    rec["updated_at"] = _now_iso()
                    updated = DroneMissionPlan.model_validate(rec)
            if updated is not None:
                self._rewrite(self._missions_path, records)
        return updated

    def get_mission(self, mission_id: str) -> DroneMissionPlan | None:
        """Return the mission plan with *mission_id*, or None."""
        for rec in self._read_all(self._missions_path):
            if rec.get("mission_id") == mission_id:
                return DroneMissionPlan.model_validate(rec)
        return None

    def list_missions(
        self,
        status: DroneMissionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DroneMissionPlan]:
        """Return missions, optionally filtered by *status*."""
        records = self._read_all(self._missions_path)
        if status is not None:
            records = [r for r in records if r.get("status") == status.value]
        records = records[offset: offset + limit]
        return [DroneMissionPlan.model_validate(r) for r in records]

    def delete_mission(self, mission_id: str) -> bool:
        """Remove a mission record; return True if found."""
        with self._lock:
            records = self._read_all(self._missions_path)
            before = len(records)
            records = [r for r in records if r.get("mission_id") != mission_id]
            if len(records) < before:
                self._rewrite(self._missions_path, records)
                return True
        return False

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def start_session(self, session: DroneMissionSession) -> DroneMissionSession:
        """Persist a new mission execution session."""
        with self._lock:
            self._append(self._sessions_path, session.model_dump(mode="json"))
        return session

    def update_session(self, session_id: str, updates: dict[str, Any]) -> DroneMissionSession | None:
        """Apply *updates* to the session identified by *session_id*."""
        with self._lock:
            records = self._read_all(self._sessions_path)
            updated = None
            for rec in records:
                if rec.get("session_id") == session_id:
                    rec.update(updates)
                    rec["updated_at"] = _now_iso()
                    updated = DroneMissionSession.model_validate(rec)
            if updated is not None:
                self._rewrite(self._sessions_path, records)
        return updated

    def get_session(self, session_id: str) -> DroneMissionSession | None:
        """Return the session with *session_id*, or None."""
        for rec in self._read_all(self._sessions_path):
            if rec.get("session_id") == session_id:
                return DroneMissionSession.model_validate(rec)
        return None

    def list_sessions(
        self,
        mission_id: str | None = None,
        status: DroneMissionStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DroneMissionSession]:
        """Return sessions, optionally filtered by *mission_id* / *status*."""
        records = self._read_all(self._sessions_path)
        if mission_id is not None:
            records = [r for r in records if r.get("mission_id") == mission_id]
        if status is not None:
            records = [r for r in records if r.get("status") == status.value]
        records = records[offset: offset + limit]
        return [DroneMissionSession.model_validate(r) for r in records]

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def append_telemetry(self, point: DroneMissionTelemetryPoint) -> None:
        """Append a single telemetry point to the telemetry log."""
        with self._lock:
            self._append(self._telemetry_path, point.model_dump(mode="json"))

    def list_telemetry(
        self,
        session_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[DroneMissionTelemetryPoint]:
        """Return telemetry points for *session_id*."""
        records = self._read_all(self._telemetry_path)
        records = [r for r in records if r.get("session_id") == session_id]
        records = records[offset: offset + limit]
        return [DroneMissionTelemetryPoint.model_validate(r) for r in records]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def append_event(self, event: DroneMissionEvent) -> None:
        """Append a mission lifecycle event."""
        with self._lock:
            self._append(self._events_path, event.model_dump(mode="json"))

    def list_events(
        self,
        session_id: str | None = None,
        mission_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[DroneMissionEvent]:
        """Return events, optionally filtered by *session_id* or *mission_id*."""
        records = self._read_all(self._events_path)
        if session_id is not None:
            records = [r for r in records if r.get("session_id") == session_id]
        if mission_id is not None:
            records = [r for r in records if r.get("mission_id") == mission_id]
        records = records[offset: offset + limit]
        return [DroneMissionEvent.model_validate(r) for r in records]

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def save_report(self, report: DroneMissionReport) -> DroneMissionReport:
        """Persist a mission report."""
        with self._lock:
            self._append(self._reports_path, report.model_dump(mode="json"))
        return report

    def get_report(self, session_id: str) -> DroneMissionReport | None:
        """Return the latest report for *session_id*, or None."""
        records = [
            r for r in self._read_all(self._reports_path)
            if r.get("session_id") == session_id
        ]
        if not records:
            return None
        return DroneMissionReport.model_validate(records[-1])

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Return a basic health snapshot of storage files."""
        try:
            mission_count = len(self._read_all(self._missions_path))
            session_count = len(self._read_all(self._sessions_path))
            return {
                "status": "healthy",
                "storage_backend": self.storage_backend,
                "mission_count": mission_count,
                "session_count": session_count,
                "checked_at": _now_iso(),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "storage_backend": self.storage_backend,
                "last_error": str(exc),
                "checked_at": _now_iso(),
            }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_repository: DroneMissionRepository | None = None
_repo_lock = threading.Lock()


def get_drone_mission_repository() -> DroneMissionRepository:
    """Return the process-wide DroneMissionRepository singleton."""
    global _repository
    if _repository is None:
        with _repo_lock:
            if _repository is None:
                _repository = DroneMissionRepository()
    return _repository
