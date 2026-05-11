from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.persistence import (
    RepositoryHealth,
    get_store_backend,
    is_production_environment,
    postgres_dsn,
    prohibit_jsonl_fallback,
)
from app.db.schema_bootstrap import bootstrap_schema
from app.models.incident_models import IncidentEventQuery, IncidentEventRecord

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_INCIDENT_REPOSITORY: "IncidentRepository | None" = None
_INCIDENT_REPOSITORY_LOCK = threading.Lock()


def _parse_iso(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _matches_query(record: IncidentEventRecord, query: IncidentEventQuery) -> bool:
    if query.source_type and record.source_type != query.source_type:
        return False
    if query.camera_id and record.camera_id != query.camera_id:
        return False
    if query.session_id and record.session_id != query.session_id:
        return False
    if query.case_id and record.case_id != query.case_id:
        return False
    if query.event_type and record.event_type != query.event_type:
        return False
    if query.severity and record.severity != query.severity:
        return False
    return True


class IncidentRepository(ABC):
    def __init__(self) -> None:
        self._last_error: str | None = None

    @property
    @abstractmethod
    def storage_backend(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def append_event(self, record: IncidentEventRecord) -> IncidentEventRecord:
        raise NotImplementedError

    @abstractmethod
    def get_event(self, event_id: str) -> IncidentEventRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, query: IncidentEventQuery | dict[str, Any] | None = None) -> list[IncidentEventRecord]:
        raise NotImplementedError

    def list_session_events(self, session_id: str, limit: int = 500) -> list[IncidentEventRecord]:
        return self.list_events({"session_id": session_id, "limit": limit})

    def list_camera_events(self, camera_id: str, limit: int = 500) -> list[IncidentEventRecord]:
        return self.list_events({"camera_id": camera_id, "limit": limit})

    def health_check(self) -> RepositoryHealth:
        status = "healthy" if self.is_available() else ("failed" if is_production_environment() else "degraded")
        return RepositoryHealth(
            store="alerts_incidents",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlIncidentRepository(IncidentRepository):
    def __init__(self, storage_dir: str) -> None:
        super().__init__()
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._storage_dir), os.W_OK)

    def append_event(self, record: IncidentEventRecord) -> IncidentEventRecord:
        payload = record.model_dump(mode="json")
        with self._lock:
            with self._log_file(record.created_at).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self._set_error(None)
        return record

    def get_event(self, event_id: str) -> IncidentEventRecord | None:
        with self._lock:
            for path in sorted(self._storage_dir.glob("incident_events_*.jsonl"), reverse=True):
                with path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        payload = IncidentEventRecord.model_validate(json.loads(line))
                        if payload.event_id == event_id:
                            return payload
        return None

    def list_events(self, query: IncidentEventQuery | dict[str, Any] | None = None) -> list[IncidentEventRecord]:
        filters = query if isinstance(query, IncidentEventQuery) else IncidentEventQuery.model_validate(query or {})
        items: list[IncidentEventRecord] = []
        with self._lock:
            for path in sorted(self._storage_dir.glob("incident_events_*.jsonl"), reverse=True):
                with path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        payload = IncidentEventRecord.model_validate(json.loads(line))
                        if not _matches_query(payload, filters):
                            continue
                        items.append(payload)
                if len(items) >= max(filters.limit * 3, 300):
                    break
        items.sort(key=lambda item: _parse_iso(item.timestamp), reverse=True)
        return items[: max(1, filters.limit)]

    def health_check(self) -> RepositoryHealth:
        health = super().health_check()
        if is_production_environment() and prohibit_jsonl_fallback():
            health.status = "degraded"
            health.last_error = health.last_error or "JSONL incident history remains a development fallback"
        return health

    def _log_file(self, created_at: str | None) -> Path:
        ts = _parse_iso(created_at) or datetime.now(timezone.utc).timestamp()
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return self._storage_dir / f"incident_events_{day}.jsonl"


class PostgresIncidentRepository(IncidentRepository):
    def __init__(self) -> None:
        super().__init__()
        self._dsn = postgres_dsn()
        self._available = False
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def append_event(self, record: IncidentEventRecord) -> IncidentEventRecord:
        query = """
            INSERT INTO incident_events (
                incident_id, event_id, source_type, camera_id, session_id, case_id,
                event_type, severity, risk_score, timestamp, frame_index, time_offset_seconds,
                track_ids, object_refs, identity_ids, summary, metadata, created_at
            )
            VALUES (
                %(incident_id)s, %(event_id)s, %(source_type)s, %(camera_id)s, %(session_id)s, %(case_id)s,
                %(event_type)s, %(severity)s, %(risk_score)s, %(timestamp)s, %(frame_index)s, %(time_offset_seconds)s,
                %(track_ids)s, %(object_refs)s, %(identity_ids)s, %(summary)s, %(metadata)s, %(created_at)s
            )
            ON CONFLICT (event_id) DO UPDATE SET
                incident_id = EXCLUDED.incident_id,
                source_type = EXCLUDED.source_type,
                camera_id = EXCLUDED.camera_id,
                session_id = EXCLUDED.session_id,
                case_id = EXCLUDED.case_id,
                event_type = EXCLUDED.event_type,
                severity = EXCLUDED.severity,
                risk_score = EXCLUDED.risk_score,
                timestamp = EXCLUDED.timestamp,
                frame_index = EXCLUDED.frame_index,
                time_offset_seconds = EXCLUDED.time_offset_seconds,
                track_ids = EXCLUDED.track_ids,
                object_refs = EXCLUDED.object_refs,
                identity_ids = EXCLUDED.identity_ids,
                summary = EXCLUDED.summary,
                metadata = EXCLUDED.metadata,
                created_at = EXCLUDED.created_at
        """
        params = record.model_dump(mode="json")
        params["track_ids"] = Json(params.get("track_ids") or [])
        params["object_refs"] = Json(params.get("object_refs") or [])
        params["identity_ids"] = Json(params.get("identity_ids") or [])
        params["metadata"] = Json(params.get("metadata") or {})
        self._execute(query, params)
        return record

    def get_event(self, event_id: str) -> IncidentEventRecord | None:
        row = self._fetchone("SELECT * FROM incident_events WHERE event_id = %(event_id)s", {"event_id": event_id})
        return self._materialize(row) if row else None

    def list_events(self, query: IncidentEventQuery | dict[str, Any] | None = None) -> list[IncidentEventRecord]:
        filters = query if isinstance(query, IncidentEventQuery) else IncidentEventQuery.model_validate(query or {})
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": max(1, filters.limit)}
        for key in ("source_type", "camera_id", "session_id", "case_id", "event_type", "severity"):
            value = getattr(filters, key)
            if value:
                clauses.append(f"{key} = %({key})s")
                params[key] = value
        rows = self._fetchall(
            f"""
            SELECT * FROM incident_events
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp DESC, created_at DESC
            LIMIT %(limit)s
            """,
            params,
        )
        return [self._materialize(row) for row in rows]

    def _materialize(self, row: dict[str, Any]) -> IncidentEventRecord:
        return IncidentEventRecord.model_validate(dict(row))

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("incident_events",))
            self._available = True
            self._set_error(None)
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))

    def _connect(self):
        return psycopg2.connect(self._dsn, connect_timeout=3, cursor_factory=RealDictCursor)

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()
        self._available = True
        self._set_error(None)

    def _fetchone(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        self._available = True
        self._set_error(None)
        return row

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        self._available = True
        self._set_error(None)
        return rows


def build_incident_repository(storage_dir: str = "storage/incidents") -> IncidentRepository:
    backend = get_store_backend("alerts_incidents", default_dev="jsonl", default_prod="postgres").lower()
    if is_production_environment() and backend == "postgres":
        return PostgresIncidentRepository()
    if backend == "postgres":
        try:
            return PostgresIncidentRepository()
        except Exception:
            pass
    return JsonlIncidentRepository(str((PROJECT_ROOT / storage_dir).resolve()))


def get_incident_repository() -> IncidentRepository:
    global _INCIDENT_REPOSITORY
    with _INCIDENT_REPOSITORY_LOCK:
        if _INCIDENT_REPOSITORY is None:
            _INCIDENT_REPOSITORY = build_incident_repository()
        return _INCIDENT_REPOSITORY


def reset_incident_repository() -> None:
    global _INCIDENT_REPOSITORY
    with _INCIDENT_REPOSITORY_LOCK:
        _INCIDENT_REPOSITORY = None
