from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UserRole(Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"


class UserStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class AuditAction(Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    CAMERA_VIEWED = "camera_viewed"
    CAMERA_CONTROLLED = "camera_controlled"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_RESOLVED = "alert_resolved"
    ALERT_ESCALATED = "alert_escalated"
    INCIDENT_VIEWED = "incident_viewed"
    INCIDENT_UPDATED = "incident_updated"
    IDENTITY_VIEWED = "identity_viewed"
    IDENTITY_CREATED = "identity_created"
    IDENTITY_UPDATED = "identity_updated"
    FACE_ENROLLED = "face_enrolled"
    WATCHLIST_UPDATED = "watchlist_updated"
    MODEL_UPDATED = "model_updated"
    FORENSIC_REPLAY_VIEWED = "forensic_replay_viewed"
    MAP_VIEWED = "map_viewed"
    ACCESS_DENIED = "access_denied"
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DENIED = "websocket_denied"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"


SENSITIVE_AUDIT_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "authorization",
    "secret",
    "jwt",
    "embedding",
    "embeddings",
    "embedding_vector",
    "embedding_vector_ref",
    "image_path",
    "enrollment_image_path",
    "file_path",
    "frame_path",
    "annotated_frame_path",
}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_AUDIT_KEYS:
                continue
            if any(marker in lowered for marker in ("password", "token", "secret", "authorization", "embedding")):
                continue
            cleaned[key_text] = sanitize_metadata(item)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [sanitize_metadata(item) for item in value]
    return _json_safe(value)


@dataclass
class UserAccount:
    user_id: str
    username: str
    display_name: str | None
    role: str
    status: str
    password_hash: str
    created_at: float
    updated_at: float
    last_login_at: float | None = None
    failed_login_count: int = 0
    metadata: dict = field(default_factory=dict)
    must_change_password: bool = False
    password_changed_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
            "failed_login_count": self.failed_login_count,
            "metadata": sanitize_metadata(self.metadata),
            "must_change_password": self.must_change_password,
            "password_changed_at": self.password_changed_at,
        }

    def to_record(self) -> dict:
        data = self.to_dict()
        data["password_hash"] = self.password_hash
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "UserAccount":
        return cls(
            user_id=str(data.get("user_id") or uuid.uuid4()),
            username=str(data["username"]),
            display_name=data.get("display_name"),
            role=str(data.get("role") or UserRole.VIEWER.value),
            status=str(data.get("status") or UserStatus.ACTIVE.value),
            password_hash=str(data.get("password_hash") or ""),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            last_login_at=data.get("last_login_at"),
            failed_login_count=int(data.get("failed_login_count") or 0),
            metadata=dict(data.get("metadata") or {}),
            must_change_password=bool(data.get("must_change_password", False)),
            password_changed_at=data.get("password_changed_at"),
        )


@dataclass
class AuthToken:
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 0

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in_seconds": self.expires_in_seconds,
        }


@dataclass
class Permission:
    name: str
    description: str | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description}


@dataclass
class AuditLogEntry:
    audit_id: str
    timestamp: float
    user_id: str | None
    username: str | None
    role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    user_agent: str | None
    success: bool
    detail: str | None
    metadata: dict = field(default_factory=dict)
    previous_hash: str | None = None
    entry_hash: str | None = None

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "detail": self.detail,
            "metadata": sanitize_metadata(self.metadata),
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuditLogEntry":
        return cls(
            audit_id=str(data.get("audit_id") or uuid.uuid4()),
            timestamp=float(data.get("timestamp") or time.time()),
            user_id=data.get("user_id"),
            username=data.get("username"),
            role=data.get("role"),
            action=str(data.get("action") or ""),
            resource_type=data.get("resource_type"),
            resource_id=data.get("resource_id"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            success=bool(data.get("success", True)),
            detail=data.get("detail"),
            metadata=dict(data.get("metadata") or {}),
            previous_hash=data.get("previous_hash"),
            entry_hash=data.get("entry_hash"),
        )


@dataclass
class PrivacyPolicy:
    mask_identity_display_for_viewer: bool = True
    hide_watchlist_reason_for_operator: bool = True
    allow_raw_enrollment_image_access: bool = False
    audit_forensic_access: bool = True

    def to_dict(self) -> dict:
        return {
            "mask_identity_display_for_viewer": self.mask_identity_display_for_viewer,
            "hide_watchlist_reason_for_operator": self.hide_watchlist_reason_for_operator,
            "allow_raw_enrollment_image_access": self.allow_raw_enrollment_image_access,
            "audit_forensic_access": self.audit_forensic_access,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "PrivacyPolicy":
        payload = data or {}
        return cls(
            mask_identity_display_for_viewer=bool(payload.get("mask_identity_display_for_viewer", True)),
            hide_watchlist_reason_for_operator=bool(payload.get("hide_watchlist_reason_for_operator", True)),
            allow_raw_enrollment_image_access=bool(payload.get("allow_raw_enrollment_image_access", False)),
            audit_forensic_access=bool(payload.get("audit_forensic_access", True)),
        )
