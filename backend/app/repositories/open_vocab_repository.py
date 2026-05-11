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

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some test environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


def _parse_created_at(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class OpenVocabResultRepository(ABC):
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
    def append_result(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_result(self, scan_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_by_incident(self, incident_id: str, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        if self.is_available():
            status = "healthy"
        else:
            status = "failed" if is_production_environment() else "degraded"
        return RepositoryHealth(
            store="open_vocab_results",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlOpenVocabResultRepository(OpenVocabResultRepository):
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

    def health_check(self) -> RepositoryHealth:
        health = super().health_check()
        if is_production_environment() and prohibit_jsonl_fallback():
            health.status = "degraded"
            health.last_error = health.last_error or "JSONL open-vocab persistence remains a development fallback"
        return health

    def append_result(self, record: dict[str, Any]) -> None:
        with self._lock:
            with self._log_file(record.get("created_at")).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with self._lock:
            for path in sorted(self._storage_dir.glob("open_vocab_*.jsonl"), reverse=True):
                with path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        items.append(json.loads(line))
                if len(items) >= limit * 3:
                    break
        items.sort(key=lambda item: _parse_created_at(item.get("created_at")), reverse=True)
        return items[: max(1, limit)]

    def get_result(self, scan_id: str) -> dict[str, Any] | None:
        with self._lock:
            for path in sorted(self._storage_dir.glob("open_vocab_*.jsonl"), reverse=True):
                with path.open("r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if record.get("scan_id") == scan_id:
                            return record
        return None

    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict[str, Any]]:
        items = [item for item in self.list_recent(limit=max(limit * 5, 100)) if item.get("camera_id") == camera_id]
        return items[: max(1, limit)]

    def list_by_incident(self, incident_id: str, limit: int = 100) -> list[dict[str, Any]]:
        items = [item for item in self.list_recent(limit=max(limit * 5, 100)) if item.get("incident_id") == incident_id]
        return items[: max(1, limit)]

    def _log_file(self, created_at: Any) -> Path:
        dt = datetime.fromtimestamp(_parse_created_at(created_at) or datetime.now(timezone.utc).timestamp(), tz=timezone.utc)
        return self._storage_dir / f"open_vocab_{dt.strftime('%Y-%m-%d')}.jsonl"


class PostgresOpenVocabResultRepository(OpenVocabResultRepository):
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

    def append_result(self, record: dict[str, Any]) -> None:
        query = """
            INSERT INTO open_vocab_results (
                scan_id, camera_id, incident_id, created_at, updated_at,
                risk_score, detections, prompts, metadata
            )
            VALUES (
                %(scan_id)s, %(camera_id)s, %(incident_id)s, %(created_at)s, %(updated_at)s,
                %(risk_score)s, %(detections)s, %(prompts)s, %(metadata)s
            )
            ON CONFLICT (scan_id) DO UPDATE SET
                camera_id = EXCLUDED.camera_id,
                incident_id = EXCLUDED.incident_id,
                updated_at = EXCLUDED.updated_at,
                risk_score = EXCLUDED.risk_score,
                detections = EXCLUDED.detections,
                prompts = EXCLUDED.prompts,
                metadata = EXCLUDED.metadata
        """
        created_at = str(record.get("created_at") or datetime.now(timezone.utc).isoformat())
        params = {
            "scan_id": str(record.get("scan_id") or ""),
            "camera_id": record.get("camera_id"),
            "incident_id": record.get("incident_id"),
            "created_at": created_at,
            "updated_at": created_at,
            "risk_score": record.get("risk_score"),
            "detections": Json(record.get("detections") or []),
            "prompts": Json(record.get("prompts") or record.get("prompt_hits") or []),
            "metadata": Json({"payload": record}),
        }
        self._execute(query, params)

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM open_vocab_results
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return [self._materialize_row(row) for row in self._fetchall(query, {"limit": max(1, limit)})]

    def get_result(self, scan_id: str) -> dict[str, Any] | None:
        query = "SELECT * FROM open_vocab_results WHERE scan_id = %(scan_id)s"
        row = self._fetchone(query, {"scan_id": scan_id})
        return self._materialize_row(row) if row else None

    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM open_vocab_results
            WHERE camera_id = %(camera_id)s
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return [self._materialize_row(row) for row in self._fetchall(query, {"camera_id": camera_id, "limit": max(1, limit)})]

    def list_by_incident(self, incident_id: str, limit: int = 100) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM open_vocab_results
            WHERE incident_id = %(incident_id)s
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return [self._materialize_row(row) for row in self._fetchall(query, {"incident_id": incident_id, "limit": max(1, limit)})]

    def _materialize_row(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return {}
        payload = dict((row.get("metadata") or {}).get("payload") or {})
        if payload:
            return payload
        return {
            "scan_id": row.get("scan_id"),
            "camera_id": row.get("camera_id"),
            "incident_id": row.get("incident_id"),
            "created_at": row.get("created_at"),
            "risk_score": row.get("risk_score"),
            "detections": row.get("detections") or [],
            "prompts": row.get("prompts") or [],
        }

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("open_vocab_results",))
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


def build_open_vocab_result_repository(storage_dir: str) -> OpenVocabResultRepository:
    backend = get_store_backend("open_vocab_results", default_dev="jsonl", default_prod="postgres").lower()
    if is_production_environment() and backend == "postgres":
        return PostgresOpenVocabResultRepository()
    return JsonlOpenVocabResultRepository(storage_dir)
