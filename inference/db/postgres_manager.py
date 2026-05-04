from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from inference.monitoring.metrics import get_metrics

_WEAPON_KEYWORDS = frozenset({"WEAPON", "ARMED", "GUN", "RIFLE", "PISTOL", "KNIFE", "GRENADE", "SHOTGUN"})

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_postgres_dsn(dsn: str | None) -> str | None:
    if not dsn:
        return None
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    return None


_DDL = """
CREATE TABLE IF NOT EXISTS tracks (
    track_id UUID PRIMARY KEY,
    identity_id UUID NOT NULL,
    local_track_id BIGINT,
    camera_id TEXT NOT NULL,
    bbox JSONB NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    class_name TEXT,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_tracks_identity_id ON tracks (identity_id);
CREATE INDEX IF NOT EXISTS idx_tracks_camera_id ON tracks (camera_id);

CREATE TABLE IF NOT EXISTS events (
    event_id UUID PRIMARY KEY,
    track_id UUID,
    event_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    severity TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events (severity);

CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id UUID PRIMARY KEY,
    event_cluster JSONB NOT NULL,
    scenario_type TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_scenarios_status ON scenarios (status);
CREATE INDEX IF NOT EXISTS idx_scenarios_risk ON scenarios (risk_level);
"""


class PostgresManager:
    """
    Non-blocking PostgreSQL persistence manager with required startup health.

    Public write calls update an in-memory cache immediately and enqueue an
    async database write for a background worker.
    """

    def __init__(self, dsn: str | None = None, queue_size: int = 4096) -> None:
        raw_dsn = dsn or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
        if raw_dsn is None:
            raw_dsn = os.getenv("DB_URL")
        if raw_dsn is None:
            raise RuntimeError("PostgreSQL is required for system operation")
        self._dsn = _coerce_postgres_dsn(raw_dsn)
        if self._dsn is None:
            raise RuntimeError("PostgreSQL is required for system operation")
        self._queue_size = queue_size
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._engine: AsyncEngine | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._thread: threading.Thread | None = None
        self._enabled = True
        self._db_healthy = False
        self._startup_error: Exception | None = None
        self._tracks_by_uuid: dict[str, dict[str, Any]] = {}
        self._tracks_by_local: dict[int, dict[str, Any]] = {}
        self._events: dict[str, dict[str, Any]] = {}
        self._scenarios: dict[str, dict[str, Any]] = {}

        self._thread = threading.Thread(
            target=self._run_worker,
            name="aegis-postgres-writer",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=15.0)
        if not self._ready.is_set():
            raise RuntimeError("PostgreSQL is required for system operation")
        if self._startup_error is not None:
            raise RuntimeError("PostgreSQL is required for system operation") from self._startup_error
        if not self._db_healthy:
            raise RuntimeError("PostgreSQL is required for system operation")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def healthy(self) -> bool:
        return self._db_healthy

    def upsert_track(self, record: dict[str, Any]) -> None:
        with self._lock:
            copied = deepcopy(record)
            self._tracks_by_uuid[copied["track_id"]] = copied
            local_track_id = copied.get("local_track_id")
            if local_track_id is not None:
                self._tracks_by_local[int(local_track_id)] = copied
        self._publish({"kind": "track_upsert", "record": copied})

    def insert_event(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._events[record["event_id"]] = deepcopy(record)
        self._publish({"kind": "event_insert", "record": deepcopy(record)})

    def insert_scenario(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._scenarios[record["scenario_id"]] = deepcopy(record)
        self._publish({"kind": "scenario_insert", "record": deepcopy(record)})

    def update_scenario_status(self, scenario_id: str, status: str, end_time: str | None = None) -> None:
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if scenario is None:
                return
            scenario["status"] = status
            scenario["end_time"] = end_time
        self._publish(
            {
                "kind": "scenario_status",
                "record": {
                    "scenario_id": scenario_id,
                    "status": status,
                    "end_time": end_time,
                },
            }
        )

    def query_track_history(self, track_id: int | str) -> dict[str, Any] | None:
        with self._lock:
            if isinstance(track_id, int):
                record = self._tracks_by_local.get(track_id)
            else:
                record = self._tracks_by_uuid.get(track_id)
            return deepcopy(record) if record else None

    def get_active_threats(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                deepcopy(record)
                for record in self._events.values()
                if record.get("severity") in {"HIGH", "CRITICAL"}
            ]
        rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
        return rows[:limit]

    def get_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [deepcopy(record) for record in self._events.values()]
        if event_type:
            rows = [row for row in rows if row.get("event_type") == event_type]
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
        return rows[:limit]

    def get_scenarios(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = [deepcopy(record) for record in self._scenarios.values()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: row.get("start_time", ""), reverse=True)
        return rows[:limit]

    # ── unified fetch API (used by REST layer) ──────────────────────────────────

    def fetch_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* events, newest first."""
        return self.get_events(limit=limit)

    def fetch_tracks(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* tracks by last_seen, newest first."""
        with self._lock:
            rows = [deepcopy(record) for record in self._tracks_by_uuid.values()]
        rows.sort(key=lambda row: row.get("last_seen", ""), reverse=True)
        return rows[:limit]

    def fetch_scenarios(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* scenarios by start_time, newest first."""
        return self.get_scenarios(limit=limit)

    def close(self) -> None:
        self._stop.set()
        if self._enabled and self._loop is not None:
            self._publish({"kind": "shutdown"})
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    async def _safe_enqueue(self, op: dict[str, Any]) -> None:
        """
        Enqueue *op* with priority-aware backpressure.

        Priority rules when the queue is full:
          KEEP  — weapon-related events (retry with 0.5 s timeout)
          DROP  — low-confidence events (confidence < 0.4)
          DROP  — all other non-event writes
        """
        try:
            self._queue.put_nowait(op)
            return
        except asyncio.QueueFull:
            pass

        record = op.get("record", {})
        kind = op.get("kind", "")
        event_type = str(record.get("event_type", "")).upper()
        confidence = float(record.get("confidence", 1.0))
        is_weapon = any(kw in event_type for kw in _WEAPON_KEYWORDS)

        if is_weapon:
            try:
                await asyncio.wait_for(self._queue.put(op), timeout=0.5)
                logger.warning(
                    "PostgreSQL queue full — weapon event enqueued after brief wait (event_type=%s).",
                    event_type,
                )
                return
            except (asyncio.TimeoutError, Exception) as exc:
                logger.error(
                    "CRITICAL: PostgreSQL queue full — WEAPON event DROPPED "
                    "(event_type=%s, error=%s).",
                    event_type, exc,
                )
        elif kind != "event_insert" or confidence < 0.4:
            logger.warning(
                "PostgreSQL write queue full (%d/%d) — dropping low-priority op '%s' "
                "(confidence=%.2f).",
                self._queue.qsize(), self._queue_size, kind, confidence,
            )
        else:
            logger.warning(
                "PostgreSQL write queue full (%d/%d) — dropping op '%s'.",
                self._queue.qsize(), self._queue_size, kind,
            )

        get_metrics().increment("events_dropped")

    def _publish(self, op: dict[str, Any]) -> None:
        if not self._enabled or self._loop is None or self._queue is None:
            logger.warning("PostgreSQL writer unavailable — dropping write op '%s'.", op.get("kind"))
            return
        if not self._db_healthy:
            logger.warning("PostgreSQL unhealthy — dropping write op '%s'.", op.get("kind"))
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._safe_enqueue(op), self._loop)
            future.result(timeout=2.0)
        except Exception as exc:
            logger.warning(
                "PostgreSQL write dropped — enqueue failed for op '%s': %s",
                op.get("kind"), exc,
            )

    def _run_worker(self) -> None:
        asyncio.run(self._worker_main())

    async def _worker_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        try:
            self._engine = create_async_engine(self._dsn, pool_pre_ping=True)
            await self._initialise_schema()
            self._db_healthy = True
            logger.info("PostgresManager async writer is online.")
        except Exception as exc:
            self._db_healthy = False
            self._startup_error = exc
            logger.exception("PostgresManager failed to initialise.")
        finally:
            self._ready.set()

        while not self._stop.is_set():
            op = await self._queue.get()
            if op.get("kind") == "shutdown":
                self._queue.task_done()
                break
            if not self._db_healthy or self._engine is None:
                self._queue.task_done()
                raise RuntimeError("PostgreSQL writer became unhealthy during runtime.")
            try:
                await self._execute(op)
            except Exception as exc:
                self._db_healthy = False
                self._startup_error = exc
                logger.exception("PostgresManager write failed for op %s", op.get("kind"))
                raise
            finally:
                self._queue.task_done()

        if self._engine is not None:
            await self._engine.dispose()

    async def _initialise_schema(self) -> None:
        if self._engine is None:
            return
        async with self._engine.begin() as conn:
            for statement in filter(None, (part.strip() for part in _DDL.split(";"))):
                await conn.execute(text(statement))

    async def _execute(self, op: dict[str, Any]) -> None:
        kind = op["kind"]
        record = op["record"]
        if kind == "track_upsert":
            await self._execute_track_upsert(record)
            return
        if kind == "event_insert":
            await self._execute_event_insert(record)
            return
        if kind == "scenario_insert":
            await self._execute_scenario_insert(record)
            return
        if kind == "scenario_status":
            await self._execute_scenario_status(record)

    async def _execute_track_upsert(self, record: dict[str, Any]) -> None:
        if self._engine is None:
            return
        stmt = text(
            """
            INSERT INTO tracks (
                track_id, identity_id, local_track_id, camera_id, bbox,
                start_time, last_seen, status, class_name, confidence, metadata
            ) VALUES (
                :track_id, :identity_id, :local_track_id, :camera_id, CAST(:bbox AS JSONB),
                :start_time, :last_seen, :status, :class_name, :confidence, CAST(:metadata AS JSONB)
            )
            ON CONFLICT (track_id) DO UPDATE SET
                identity_id = EXCLUDED.identity_id,
                local_track_id = EXCLUDED.local_track_id,
                camera_id = EXCLUDED.camera_id,
                bbox = EXCLUDED.bbox,
                last_seen = EXCLUDED.last_seen,
                status = EXCLUDED.status,
                class_name = EXCLUDED.class_name,
                confidence = EXCLUDED.confidence,
                metadata = EXCLUDED.metadata
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                stmt,
                {
                    "track_id": record["track_id"],
                    "identity_id": record["identity_id"],
                    "local_track_id": record.get("local_track_id"),
                    "camera_id": record.get("camera_id", "default"),
                    "bbox": json.dumps(record.get("bbox", [])),
                    "start_time": record.get("start_time", _now_iso()),
                    "last_seen": record.get("last_seen", _now_iso()),
                    "status": record.get("status", "ACTIVE"),
                    "class_name": record.get("class_name"),
                    "confidence": float(record.get("confidence", 0.0)),
                    "metadata": json.dumps(record.get("metadata", {})),
                },
            )

    async def _execute_event_insert(self, record: dict[str, Any]) -> None:
        if self._engine is None:
            return
        stmt = text(
            """
            INSERT INTO events (
                event_id, track_id, event_type, confidence, risk_score,
                timestamp, severity, metadata
            ) VALUES (
                :event_id, :track_id, :event_type, :confidence, :risk_score,
                :timestamp, :severity, CAST(:metadata AS JSONB)
            )
            ON CONFLICT (event_id) DO NOTHING
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                stmt,
                {
                    "event_id": record["event_id"],
                    "track_id": record.get("track_id"),
                    "event_type": record.get("event_type"),
                    "confidence": float(record.get("confidence", 0.0)),
                    "risk_score": float(record.get("risk_score", 0.0)),
                    "timestamp": record.get("timestamp", _now_iso()),
                    "severity": record.get("severity", "LOW"),
                    "metadata": json.dumps(record.get("metadata", {})),
                },
            )

    async def _execute_scenario_insert(self, record: dict[str, Any]) -> None:
        if self._engine is None:
            return
        stmt = text(
            """
            INSERT INTO scenarios (
                scenario_id, event_cluster, scenario_type, risk_level,
                status, start_time, end_time, metadata
            ) VALUES (
                :scenario_id, CAST(:event_cluster AS JSONB), :scenario_type, :risk_level,
                :status, :start_time, :end_time, CAST(:metadata AS JSONB)
            )
            ON CONFLICT (scenario_id) DO UPDATE SET
                event_cluster = EXCLUDED.event_cluster,
                scenario_type = EXCLUDED.scenario_type,
                risk_level = EXCLUDED.risk_level,
                status = EXCLUDED.status,
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                metadata = EXCLUDED.metadata
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                stmt,
                {
                    "scenario_id": record["scenario_id"],
                    "event_cluster": json.dumps(record.get("event_cluster", [])),
                    "scenario_type": record.get("scenario_type"),
                    "risk_level": record.get("risk_level", "LOW"),
                    "status": record.get("status", "ACTIVE"),
                    "start_time": record.get("start_time", _now_iso()),
                    "end_time": record.get("end_time"),
                    "metadata": json.dumps(record.get("metadata", {})),
                },
            )

    async def _execute_scenario_status(self, record: dict[str, Any]) -> None:
        if self._engine is None:
            return
        stmt = text(
            """
            UPDATE scenarios
            SET status = :status, end_time = :end_time
            WHERE scenario_id = :scenario_id
            """
        )
        async with self._engine.begin() as conn:
            await conn.execute(
                stmt,
                {
                    "scenario_id": record["scenario_id"],
                    "status": record["status"],
                    "end_time": record.get("end_time"),
                },
            )
