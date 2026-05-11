from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from app.core.persistence import is_production_environment, store_required_in_production
from app.models.security_models import AuditAction, AuditLogEntry, UserAccount, sanitize_metadata
from app.repositories.audit_repository import AuditLogRepository, build_audit_log_repository
from app.security.config import get_audit_config

logger = logging.getLogger(__name__)


class AuditLogService:
    def __init__(
        self,
        config: dict | None = None,
        *,
        repository: AuditLogRepository | None = None,
    ) -> None:
        self._config = config or get_audit_config()
        self._enabled = bool(self._config.get("enabled", True))
        self._hash_chain_enabled = bool(self._config.get("hash_chain_enabled", True))
        self._repository = repository or build_audit_log_repository(self._config)

    @property
    def repository(self) -> AuditLogRepository:
        return self._repository

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
            self._repository.append(entry, hash_chain_enabled=self._hash_chain_enabled)
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
            if is_production_environment() and store_required_in_production("audit_logs"):
                raise RuntimeError("Audit log persistence is required in production") from exc
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
        entries = self._repository.list_entries(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return [entry.to_dict() for entry in entries]

    def get_recent(self, limit: int = 100) -> list[dict]:
        return [entry.to_dict() for entry in self._repository.get_recent_entries(limit=limit)]

    def verify_integrity(self) -> dict:
        try:
            from inference.metrics import metrics

            metrics.increment("audit_integrity_checks")
        except Exception:
            pass

        result = self._repository.verify_integrity()
        if result.get("broken_files"):
            try:
                from inference.metrics import metrics

                metrics.increment("audit_integrity_failures")
            except Exception:
                pass
        return result

    def health(self) -> dict[str, Any]:
        payload = self._repository.health_check().to_dict()
        payload["storage"] = payload.pop("backend")
        payload["hash_chain_enabled"] = self._hash_chain_enabled
        return payload


_audit_log_service: AuditLogService | None = None
_audit_log_lock = threading.Lock()


def get_audit_log_service() -> AuditLogService:
    global _audit_log_service
    if _audit_log_service is None:
        with _audit_log_lock:
            if _audit_log_service is None:
                _audit_log_service = AuditLogService()
    return _audit_log_service


def set_audit_log_service(service: AuditLogService) -> None:
    global _audit_log_service
    with _audit_log_lock:
        _audit_log_service = service


def reset_audit_log_service() -> None:
    global _audit_log_service
    with _audit_log_lock:
        _audit_log_service = None
