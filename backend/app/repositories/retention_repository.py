from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.persistence import (
    RepositoryHealth,
    get_store_backend,
    is_production_environment,
    postgres_dsn,
    prohibit_jsonl_fallback,
    store_required_in_production,
)
from app.db.schema_bootstrap import bootstrap_schema

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some test environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


class RetentionActionRepository(ABC):
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
    def append_action(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_actions(self, *, case_id: str | None = None, evidence_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        if self.is_available():
            status = "healthy"
        else:
            status = "failed" if is_production_environment() else "degraded"
        return RepositoryHealth(
            store="retention_actions",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlRetentionActionRepository(RetentionActionRepository):
    def __init__(self, storage_dir: str) -> None:
        super().__init__()
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._storage_dir / "retention_actions.jsonl"
        self._lock = threading.RLock()

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._storage_dir), os.W_OK)

    def health_check(self) -> RepositoryHealth:
        health = super().health_check()
        if (
            is_production_environment()
            and store_required_in_production("retention_actions")
            and prohibit_jsonl_fallback()
        ):
            health.status = "failed"
            health.last_error = health.last_error or "JSONL fallback is prohibited for retention actions in production"
        return health

    def append_action(self, record: dict[str, Any]) -> None:
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def list_actions(self, *, case_id: str | None = None, evidence_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self._path.exists():
            return items
        with self._lock:
            with self._path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if case_id and str(record.get("case_id") or "") != str(case_id):
                        continue
                    if evidence_id and str(record.get("evidence_id") or "") != str(evidence_id):
                        continue
                    items.append(record)
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return items[: max(1, limit)]


class PostgresRetentionActionRepository(RetentionActionRepository):
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

    def append_action(self, record: dict[str, Any]) -> None:
        query = """
            INSERT INTO retention_actions (
                action_id, case_id, evidence_id, mode, status, requested_by, reviewed_by,
                review_required, storage_uri, hash_sha256, before_metadata, after_metadata,
                metadata, created_at, updated_at, action_completed_at
            )
            VALUES (
                %(action_id)s, %(case_id)s, %(evidence_id)s, %(mode)s, %(status)s, %(requested_by)s, %(reviewed_by)s,
                %(review_required)s, %(storage_uri)s, %(hash_sha256)s, %(before_metadata)s, %(after_metadata)s,
                %(metadata)s, %(created_at)s, %(updated_at)s, %(action_completed_at)s
            )
            ON CONFLICT (action_id) DO UPDATE SET
                case_id = EXCLUDED.case_id,
                evidence_id = EXCLUDED.evidence_id,
                mode = EXCLUDED.mode,
                status = EXCLUDED.status,
                requested_by = EXCLUDED.requested_by,
                reviewed_by = EXCLUDED.reviewed_by,
                review_required = EXCLUDED.review_required,
                storage_uri = EXCLUDED.storage_uri,
                hash_sha256 = EXCLUDED.hash_sha256,
                before_metadata = EXCLUDED.before_metadata,
                after_metadata = EXCLUDED.after_metadata,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at,
                action_completed_at = EXCLUDED.action_completed_at
        """
        params = {
            **record,
            "before_metadata": Json(record.get("before_metadata") or {}),
            "after_metadata": Json(record.get("after_metadata") or {}),
            "metadata": Json(record.get("metadata") or {}),
        }
        self._execute(query, params)

    def list_actions(self, *, case_id: str | None = None, evidence_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": max(1, limit)}
        if case_id:
            clauses.append("case_id = %(case_id)s")
            params["case_id"] = case_id
        if evidence_id:
            clauses.append("evidence_id = %(evidence_id)s")
            params["evidence_id"] = evidence_id
        query = f"""
            SELECT * FROM retention_actions
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return [dict(row) for row in self._fetchall(query, params)]

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("retention_actions",))
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

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        self._available = True
        self._set_error(None)
        return rows


def build_retention_action_repository(storage_dir: str) -> RetentionActionRepository:
    backend = get_store_backend("retention_actions", default_dev="jsonl", default_prod="postgres").lower()
    if is_production_environment() and backend == "postgres":
        return PostgresRetentionActionRepository()
    return JsonlRetentionActionRepository(storage_dir)
