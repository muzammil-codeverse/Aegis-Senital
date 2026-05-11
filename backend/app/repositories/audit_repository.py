from __future__ import annotations

import json
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
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
from app.models.security_models import AuditLogEntry
from app.security.audit_integrity import compute_entry_hash, verify_audit_chain
from app.security.config import get_audit_config, project_path

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


class AuditLogRepository(ABC):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or get_audit_config()
        self._enabled = bool(self._config.get("enabled", True))
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    @abstractmethod
    def storage_backend(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def append(self, entry: AuditLogEntry, *, hash_chain_enabled: bool = True) -> AuditLogEntry:
        raise NotImplementedError

    @abstractmethod
    def list_entries(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 200,
    ) -> list[AuditLogEntry]:
        raise NotImplementedError

    @abstractmethod
    def get_recent_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        raise NotImplementedError

    @abstractmethod
    def verify_integrity(self) -> dict[str, Any]:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        if not self.enabled:
            status = "disabled"
        elif self.is_available():
            status = "healthy"
        else:
            status = "failed" if is_production_environment() else "degraded"
        return RepositoryHealth(
            store="audit_logs",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
            extra={"enabled": self.enabled},
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlAuditLogRepository(AuditLogRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        storage_dir = self._config.get("storage_dir") or "storage/audit"
        self._storage_dir = project_path(str(storage_dir))
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._rotate_daily = bool(self._config.get("rotate_daily", True))
        self._lock = threading.RLock()
        self._recent: deque[AuditLogEntry] = deque(
            maxlen=int(self._config.get("max_recent_entries", 2000))
        )
        self._last_hash_by_path: dict[str, str | None] = {}
        self._load_recent()

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._storage_dir), os.W_OK)

    def health_check(self) -> RepositoryHealth:
        health = super().health_check()
        if (
            is_production_environment()
            and store_required_in_production("audit_logs")
            and prohibit_jsonl_fallback()
        ):
            health.status = "failed"
            health.last_error = health.last_error or "JSONL fallback is prohibited for audit logs in production"
        return health

    def append(self, entry: AuditLogEntry, *, hash_chain_enabled: bool = True) -> AuditLogEntry:
        with self._lock:
            path = self._path_for_timestamp(entry.timestamp)
            path_key = str(path)
            if hash_chain_enabled:
                previous_hash = self._last_hash_by_path.get(path_key)
                entry.previous_hash = previous_hash
                entry.entry_hash = compute_entry_hash(entry.to_dict(), previous_hash)
                self._last_hash_by_path[path_key] = entry.entry_hash
            payload = json.dumps(entry.to_dict(), sort_keys=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            self._recent.append(entry)
        self._set_error(None)
        return entry

    def list_entries(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 200,
    ) -> list[AuditLogEntry]:
        entries: list[AuditLogEntry] = []
        paths = sorted(self._storage_dir.glob("audit*.jsonl"), reverse=True)
        max_limit = max(1, min(int(limit), 2000))
        for path in paths:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        entry = AuditLogEntry.from_dict(json.loads(line))
                        if user_id and entry.user_id != user_id and entry.username != user_id:
                            continue
                        if action and entry.action != action:
                            continue
                        if resource_type and entry.resource_type != resource_type:
                            continue
                        if start_time is not None and entry.timestamp < start_time:
                            continue
                        if end_time is not None and entry.timestamp > end_time:
                            continue
                        entries.append(entry)
            except OSError:
                continue
        entries.sort(key=lambda item: item.timestamp, reverse=True)
        return entries[:max_limit]

    def get_recent_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        with self._lock:
            entries = list(self._recent)[-max(1, int(limit)) :]
        entries.sort(key=lambda item: item.timestamp, reverse=True)
        return entries

    def verify_integrity(self) -> dict[str, Any]:
        checked_files = 0
        broken_files: list[dict[str, Any]] = []
        latest_hash = None
        try:
            paths = sorted(self._storage_dir.glob("audit*.jsonl"))
            for path in paths:
                result = verify_audit_chain(str(path))
                checked_files += 1
                if result.get("latest_hash"):
                    latest_hash = result["latest_hash"]
                if result.get("status") == "broken":
                    broken_files.append(result)
        except Exception as exc:
            broken_files.append({"file": None, "status": "error", "detail": str(exc)})
        return {
            "status": "ok" if not broken_files else "broken",
            "checked_files": checked_files,
            "broken_files": broken_files,
            "latest_hash": latest_hash,
        }

    def _path_for_timestamp(self, timestamp: float | None = None) -> Path:
        ts = timestamp or time.time()
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if not self._rotate_daily:
            return self._storage_dir / "audit.jsonl"
        return self._storage_dir / f"audit_{day}.jsonl"

    def _load_recent(self) -> None:
        paths = sorted(self._storage_dir.glob("audit*.jsonl"))[-3:]
        rows: list[AuditLogEntry] = []
        for path in paths:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rows.append(AuditLogEntry.from_dict(json.loads(line)))
            except OSError:
                continue
        for entry in rows[-self._recent.maxlen :]:
            self._recent.append(entry)
        for path in paths:
            self._last_hash_by_path[str(path)] = self._latest_hash_for_path(path)

    @staticmethod
    def _latest_hash_for_path(path: Path) -> str | None:
        latest_hash = None
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        value = json.loads(line).get("entry_hash")
                    except json.JSONDecodeError:
                        continue
                    if value:
                        latest_hash = str(value)
        except OSError:
            return None
        return latest_hash


class PostgresAuditLogRepository(AuditLogRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._dsn = postgres_dsn()
        self._available = False
        self._latest_hash: str | None = None
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def append(self, entry: AuditLogEntry, *, hash_chain_enabled: bool = True) -> AuditLogEntry:
        if not self._available:
            raise RuntimeError(self._last_error or "Audit repository is unavailable")
        if hash_chain_enabled:
            entry.previous_hash = self._latest_hash
            entry.entry_hash = compute_entry_hash(entry.to_dict(), entry.previous_hash)
        query = """
            INSERT INTO system_audit_logs (
                audit_id, timestamp, created_at, user_id, username, role, action,
                resource_type, resource_id, ip_address, user_agent, success,
                detail, previous_hash, entry_hash, metadata
            )
            VALUES (
                %(audit_id)s, %(timestamp)s, TO_TIMESTAMP(%(timestamp)s), %(user_id)s, %(username)s, %(role)s, %(action)s,
                %(resource_type)s, %(resource_id)s, %(ip_address)s, %(user_agent)s, %(success)s,
                %(detail)s, %(previous_hash)s, %(entry_hash)s, %(metadata)s
            )
        """
        self._execute(query, {**entry.to_dict(), "metadata": Json(entry.metadata)})
        self._latest_hash = entry.entry_hash
        return entry

    def list_entries(
        self,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 200,
    ) -> list[AuditLogEntry]:
        if not self._available:
            return []
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 2000))}
        if user_id:
            clauses.append("(user_id = %(user_id)s OR username = %(user_id)s)")
            params["user_id"] = user_id
        if action:
            clauses.append("action = %(action)s")
            params["action"] = action
        if resource_type:
            clauses.append("resource_type = %(resource_type)s")
            params["resource_type"] = resource_type
        if start_time is not None:
            clauses.append("timestamp >= %(start_time)s")
            params["start_time"] = float(start_time)
        if end_time is not None:
            clauses.append("timestamp <= %(end_time)s")
            params["end_time"] = float(end_time)
        query = f"""
            SELECT audit_id, timestamp, user_id, username, role, action, resource_type, resource_id,
                   ip_address, user_agent, success, detail, metadata, previous_hash, entry_hash
            FROM system_audit_logs
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp DESC
            LIMIT %(limit)s
        """
        rows = self._fetchall(query, params)
        return [AuditLogEntry.from_dict(dict(row)) for row in rows]

    def get_recent_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        return self.list_entries(limit=limit)

    def verify_integrity(self) -> dict[str, Any]:
        if not self._available:
            return {
                "status": "error",
                "checked_files": 0,
                "broken_files": [{"file": "postgres", "status": "error", "detail": self._last_error}],
                "latest_hash": None,
            }
        query = """
            SELECT audit_id, timestamp, user_id, username, role, action, resource_type, resource_id,
                   ip_address, user_agent, success, detail, metadata, previous_hash, entry_hash
            FROM system_audit_logs
            ORDER BY timestamp ASC, audit_id ASC
        """
        rows = self._fetchall(query, {})
        previous_hash = None
        for row in rows:
            entry = AuditLogEntry.from_dict(dict(row))
            expected_hash = compute_entry_hash(entry.to_dict(), previous_hash)
            if entry.previous_hash != previous_hash or entry.entry_hash != expected_hash:
                return {
                    "status": "broken",
                    "checked_files": 1,
                    "broken_files": [{"file": "postgres", "status": "broken", "detail": entry.audit_id}],
                    "latest_hash": previous_hash,
                }
            previous_hash = entry.entry_hash
        return {
            "status": "ok",
            "checked_files": 1,
            "broken_files": [],
            "latest_hash": previous_hash,
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
                bootstrap_schema(conn, ("system_audit_logs",))
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT entry_hash
                        FROM system_audit_logs
                        ORDER BY timestamp DESC, audit_id DESC
                        LIMIT 1
                        """
                    )
                    row = cursor.fetchone()
                    if row:
                        self._latest_hash = str(row["entry_hash"] if isinstance(row, dict) else row[0])
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


def build_audit_log_repository(config: dict[str, Any] | None = None) -> AuditLogRepository:
    audit_cfg = config or get_audit_config()
    if is_production_environment():
        backend = get_store_backend("audit_logs", default_dev="jsonl", default_prod="postgres").lower()
        if backend == "postgres":
            return PostgresAuditLogRepository(config=audit_cfg)
    return JsonlAuditLogRepository(config=audit_cfg)
