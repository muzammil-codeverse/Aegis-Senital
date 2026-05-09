from __future__ import annotations

from fastapi import HTTPException

from app.models.security_models import UserAccount

FULL_ACCESS_ROLES = {"admin", "supervisor"}


def _matches_future_zone_policy(user: UserAccount | None, resource_metadata: dict | None) -> bool:
    return True


def _has_base_access(user: UserAccount | None, resource_metadata: dict | None = None) -> bool:
    if user is None:
        return False
    if user.role in FULL_ACCESS_ROLES:
        return True
    return _matches_future_zone_policy(user, resource_metadata or {})


def can_access_camera(user, camera_id: str) -> bool:
    return _has_base_access(user, {"camera_id": camera_id})


def can_access_identity(user, identity_id: str) -> bool:
    return _has_base_access(user, {"identity_id": identity_id})


def can_access_incident(user, incident_id: str) -> bool:
    return _has_base_access(user, {"incident_id": incident_id})


def can_access_alert(user, alert_id: str) -> bool:
    return _has_base_access(user, {"alert_id": alert_id})


def _raise_denied(resource: str) -> None:
    raise HTTPException(
        status_code=403,
        detail={"status": "error", "detail": f"Access denied for {resource}"},
    )


def require_camera_access(user, camera_id: str):
    if not can_access_camera(user, camera_id):
        _raise_denied("camera")
    return True


def require_identity_access(user, identity_id: str):
    if not can_access_identity(user, identity_id):
        _raise_denied("identity")
    return True


def require_incident_access(user, incident_id: str):
    if not can_access_incident(user, incident_id):
        _raise_denied("incident")
    return True


def require_alert_access(user, alert_id: str):
    if not can_access_alert(user, alert_id):
        _raise_denied("alert")
    return True
