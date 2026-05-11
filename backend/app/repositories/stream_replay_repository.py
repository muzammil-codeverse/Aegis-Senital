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
)
from app.db.schema_bootstrap import bootstrap_schema

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some test environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


def _created_at_key(item: dict[str, Any]) -> str:
    return str(item.get("created_at") or "")


class StreamReplayRepository(ABC):
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
    def save_metadata(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, clip_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        if self.is_available():
            status = "healthy"
        else:
            status = "failed" if is_production_environment() else "degraded"
        return RepositoryHealth(
            store="stream_replay_metadata",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlStreamReplayRepository(StreamReplayRepository):
    def __init__(self, storage_dir: str) -> None:
        super().__init__()
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._storage_dir / "replay_metadata.jsonl"
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        if self._index_path.exists():
            with self._index_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    self._records[str(payload["clip_id"])] = payload

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._storage_dir), os.W_OK)

    def save_metadata(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._records[str(record["clip_id"])] = dict(record)
            tmp = self._index_path.with_suffix(".jsonl.tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                for item in self._records.values():
                    handle.write(json.dumps(item, sort_keys=True) + "\n")
            tmp.replace(self._index_path)

    def get_metadata(self, clip_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(clip_id)
            return dict(record) if record is not None else None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._records.values())
        items.sort(key=_created_at_key, reverse=True)
        return [dict(item) for item in items[: max(1, limit)]]


class PostgresStreamReplayRepository(StreamReplayRepository):
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

    def save_metadata(self, record: dict[str, Any]) -> None:
        query = """
            INSERT INTO stream_replay_metadata (
                clip_id, camera_id, source_uri, file_path, metadata_path, created_at, updated_at,
                clip_start_at, clip_end_at, size_bytes, hash_sha256, integrity_status, metadata
            )
            VALUES (
                %(clip_id)s, %(camera_id)s, %(source_uri)s, %(file_path)s, %(metadata_path)s, %(created_at)s, %(updated_at)s,
                %(clip_start_at)s, %(clip_end_at)s, %(size_bytes)s, %(hash_sha256)s, %(integrity_status)s, %(metadata)s
            )
            ON CONFLICT (clip_id) DO UPDATE SET
                camera_id = EXCLUDED.camera_id,
                source_uri = EXCLUDED.source_uri,
                file_path = EXCLUDED.file_path,
                metadata_path = EXCLUDED.metadata_path,
                updated_at = EXCLUDED.updated_at,
                clip_start_at = EXCLUDED.clip_start_at,
                clip_end_at = EXCLUDED.clip_end_at,
                size_bytes = EXCLUDED.size_bytes,
                hash_sha256 = EXCLUDED.hash_sha256,
                integrity_status = EXCLUDED.integrity_status,
                metadata = EXCLUDED.metadata
        """
        params = {
            **record,
            "updated_at": record.get("created_at"),
            "metadata": Json(record.get("metadata") or {}),
        }
        self._execute(query, params)

    def get_metadata(self, clip_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM stream_replay_metadata WHERE clip_id = %(clip_id)s", {"clip_id": clip_id})
        return dict(row) if row else None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM stream_replay_metadata ORDER BY created_at DESC LIMIT %(limit)s",
            {"limit": max(1, limit)},
        )
        return [dict(row) for row in rows]

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("stream_replay_metadata",))
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


def build_stream_replay_repository(storage_dir: str) -> StreamReplayRepository:
    backend = get_store_backend("stream_replay_metadata", default_dev="jsonl", default_prod="postgres").lower()
    if is_production_environment() and backend == "postgres":
        return PostgresStreamReplayRepository()
    return JsonlStreamReplayRepository(storage_dir)
