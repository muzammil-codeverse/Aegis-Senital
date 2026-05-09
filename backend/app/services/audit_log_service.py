from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.security_models import AuditAction, AuditLogEntry, UserAccount, sanitize_metadata
from app.security.config import get_audit_config, project_path

logger = logging.getLogger(__name__)


class AuditLogService:
    def __init__(self, config: dict | None = None) -> None:
        self._config = config or get_audit_config()
        storage_dir = self._config.get("storage_dir") or "storage/audit"
        self._storage_dir = project_path(str(storage_dir))
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._enabled = bool(self._config.get("enabled", True))
        self._rotate_daily = bool(self._config.get("rotate_daily", True))
        self._lock = threading.RLock()
        self._recent: deque[AuditLogEntry] = deque(
            maxlen=int(self._config.get("max_recent_entries", 2000))
        )
        self._load_recent()

    def _path_for_timestamp(self, timestamp: float | None = None) -> Path:
        ts = timestamp or time.time()
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
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
        for entry in rows[-self._recent.maxlen:]:
            self._recent.append(entry)

    @staticmethod
    def _request_ip(request: Any) -> str | None:
        if request is None:
            return None
        forwarded = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = getattr(request, "client", None)
        return getattr(client, "host", None)

    @staticmethod
    def _request_user_agent(request: Any) -> str | None:
        if request is None or not hasattr(request, "headers"):
            return None
        user_agent = request.headers.get("user-agent")
        return user_agent[:240] if user_agent else None

    def record(
        self,
        action,
        user: UserAccount | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        success: bool = True,
        detail: str | None = None,
        request: Any = None,
        metadata: dict | None = None,
    ) -> AuditLogEntry:
        action_value = action.value if isinstance(action, AuditAction) else str(action)
        entry = AuditLogEntry(
            audit_id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_id=user.user_id if user else None,
            username=user.username if user else None,
            role=user.role if user else None,
            action=action_value,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            ip_address=self._request_ip(request),
            user_agent=self._request_user_agent(request),
            success=bool(success),
            detail=detail[:500] if isinstance(detail, str) else detail,
            metadata=sanitize_metadata(metadata or {}),
        )

        if not self._enabled:
            return entry

        try:
            payload = json.dumps(entry.to_dict(), sort_keys=True)
            with self._lock:
                path = self._path_for_timestamp(entry.timestamp)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(payload + "\n")
                self._recent.append(entry)
            try:
                from inference.metrics import metrics
                metrics.increment("audit_events_written")
            except Exception:
                pass
        except Exception as exc:
            logger.error("Audit log write failed: %s", exc)
            try:
                from inference.metrics import metrics
                metrics.increment("audit_write_failures")
            except Exception:
                pass
        return entry

    def list_logs(
        self,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 200,
    ) -> list[dict]:
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
        return [entry.to_dict() for entry in entries[:max_limit]]

    def get_recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            entries = list(self._recent)[-max(1, int(limit)):]
        entries.sort(key=lambda item: item.timestamp, reverse=True)
        return [entry.to_dict() for entry in entries]


_audit_log_service: AuditLogService | None = None
_audit_log_lock = threading.Lock()


def get_audit_log_service() -> AuditLogService:
    global _audit_log_service
    if _audit_log_service is None:
        with _audit_log_lock:
            if _audit_log_service is None:
                _audit_log_service = AuditLogService()
    return _audit_log_service
