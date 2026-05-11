from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request

from app.models.security_models import AuditAction, UserAccount
from app.security.config import auth_required
from app.services.audit_log_service import get_audit_log_service
from app.services.case_service import get_case_service
from app.services.osint_service import get_osint_service

FULL_ACCESS_ROLES = {"admin", "supervisor"}
SCOPE_KEYS = {
    "camera": "camera_scopes",
    "case": "case_scopes",
    "identity": "identity_scopes",
    "watchlist": "watchlist_scopes",
    "incident": "incident_scopes",
    "alert": "alert_scopes",
    "osint_source": "osint_source_scopes",
}


@dataclass(frozen=True)
class ObjectAccessDecision:
    allowed: bool
    reason: str
    bypass: bool = False


def _user_role(user: UserAccount | None) -> str:
    return str(getattr(user, "role", "") or "").lower()


def _metadata(user: UserAccount | None) -> dict[str, Any]:
    payload = getattr(user, "metadata", None)
    return payload if isinstance(payload, dict) else {}


def _scope_values(user: UserAccount | None, key: str) -> set[str]:
    values = _metadata(user).get(key, [])
    if isinstance(values, (list, tuple, set)):
        return {str(value).strip() for value in values if str(value).strip()}
    text = str(values or "").strip()
    return {text} if text else set()


def _has_global_access(user: UserAccount | None) -> bool:
    return bool(_metadata(user).get("global_access", False))


def _camera_region_values(camera: Any) -> set[str]:
    values: set[str] = set()
    if camera is None:
        return values
    zone = str(getattr(camera, "zone", "") or "").strip()
    if zone:
        values.add(zone)
    location = getattr(camera, "location", None) or {}
    if isinstance(location, dict):
        for key in ("region", "site_id", "city", "zone"):
            value = str(location.get(key, "") or "").strip()
            if value:
                values.add(value)
    metadata = getattr(camera, "metadata", None) or {}
    if isinstance(metadata, dict):
        for key in ("region", "site_id", "city", "zone"):
            value = str(metadata.get(key, "") or "").strip()
            if value:
                values.add(value)
    return values


def _bypass_decision(user: UserAccount | None, resource_type: str, resource_id: str) -> ObjectAccessDecision | None:
    role = _user_role(user)
    if role in FULL_ACCESS_ROLES:
        return ObjectAccessDecision(
            allowed=True,
            reason=f"explicit_{role}_bypass",
            bypass=True,
        )
    if _has_global_access(user):
        return ObjectAccessDecision(
            allowed=True,
            reason="explicit_global_access",
            bypass=False,
        )
    return None


def _deny_decision(reason: str) -> ObjectAccessDecision:
    return ObjectAccessDecision(allowed=False, reason=reason, bypass=False)


def _allow_decision(reason: str) -> ObjectAccessDecision:
    return ObjectAccessDecision(allowed=True, reason=reason, bypass=False)


def _camera_scope_decision(user: UserAccount | None, camera_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "camera", camera_id)
    if bypass:
        return bypass
    if camera_id in _scope_values(user, SCOPE_KEYS["camera"]):
        return _allow_decision("camera_scope")
    region_scopes = _scope_values(user, "region_scopes")
    if region_scopes:
        try:
            from app.services.camera_registry import get_camera_registry

            camera = get_camera_registry().get_camera(camera_id)
        except Exception:
            camera = None
        if _camera_region_values(camera) & region_scopes:
            return _allow_decision("region_scope")
    return _deny_decision("camera_scope_missing")


def _case_scope_decision(user: UserAccount | None, case_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "case", case_id)
    if bypass:
        return bypass
    if case_id in _scope_values(user, SCOPE_KEYS["case"]):
        return _allow_decision("case_scope")
    case = get_case_service().get_case(case_id)
    if case is None:
        return _deny_decision("case_not_found")
    if str(case.assigned_to or "").strip() == str(getattr(user, "username", "") or "").strip():
        return _allow_decision("case_assignee")
    for camera_id in case.camera_ids:
        decision = _camera_scope_decision(user, str(camera_id))
        if decision.allowed:
            return _allow_decision(f"case_camera_scope:{camera_id}")
    return _deny_decision("case_scope_missing")


def _find_evidence(evidence_id: str):
    service = get_case_service()
    for case in service.list_cases({"limit": 5000}):
        for item in service.list_evidence(case.case_id):
            if item.evidence_id == evidence_id:
                return item
    return None


def _case_for_evidence(evidence_id: str) -> str | None:
    evidence = _find_evidence(evidence_id)
    return getattr(evidence, "case_id", None)


def _identity_scope_decision(user: UserAccount | None, identity_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "identity", identity_id)
    if bypass:
        return bypass
    if identity_id in _scope_values(user, SCOPE_KEYS["identity"]):
        return _allow_decision("identity_scope")
    try:
        from inference.identity.identity_profile_store import get_identity_store

        matches = get_identity_store().list_matches(identity_id=identity_id, limit=500)
    except Exception:
        matches = []
    for match in matches:
        camera_id = str(getattr(match, "camera_id", "") or "").strip()
        if not camera_id:
            continue
        decision = _camera_scope_decision(user, camera_id)
        if decision.allowed:
            return _allow_decision(f"identity_camera_scope:{camera_id}")
    return _deny_decision("identity_scope_missing")


def _watchlist_scope_decision(user: UserAccount | None, watchlist_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "watchlist", watchlist_id)
    if bypass:
        return bypass
    if watchlist_id in _scope_values(user, SCOPE_KEYS["watchlist"]):
        return _allow_decision("watchlist_scope")
    try:
        from inference.identity.watchlist_store import get_watchlist_store

        entry = get_watchlist_store().get_watchlist_entry(watchlist_id)
    except Exception:
        entry = None
    if entry is None:
        return _deny_decision("watchlist_not_found")
    return _identity_scope_decision(user, str(entry.identity_id))


def _incident_scope_decision(user: UserAccount | None, incident_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "incident", incident_id)
    if bypass:
        return bypass
    if incident_id in _scope_values(user, SCOPE_KEYS["incident"]):
        return _allow_decision("incident_scope")
    try:
        from inference.runtime import get_intelligence_runtime

        incident = get_intelligence_runtime().incident_engine.get_incident(incident_id)
    except Exception:
        incident = None
    if not incident:
        return _deny_decision("incident_not_found")
    for camera_id in list(incident.get("camera_ids", [])) or []:
        decision = _camera_scope_decision(user, str(camera_id))
        if decision.allowed:
            return _allow_decision(f"incident_camera_scope:{camera_id}")
    return _deny_decision("incident_scope_missing")


def _alert_scope_decision(user: UserAccount | None, alert_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "alert", alert_id)
    if bypass:
        return bypass
    if alert_id in _scope_values(user, SCOPE_KEYS["alert"]):
        return _allow_decision("alert_scope")
    try:
        from inference.runtime import get_intelligence_runtime

        response = get_intelligence_runtime().get_alert(alert_id)
        alert = response.get("item") if isinstance(response, dict) else None
    except Exception:
        alert = None
    if not alert:
        return _deny_decision("alert_not_found")
    for camera_id in list(alert.get("camera_ids", [])) or []:
        decision = _camera_scope_decision(user, str(camera_id))
        if decision.allowed:
            return _allow_decision(f"alert_camera_scope:{camera_id}")
    for identity_id in list(alert.get("identity_ids", [])) or []:
        decision = _identity_scope_decision(user, str(identity_id))
        if decision.allowed:
            return _allow_decision(f"alert_identity_scope:{identity_id}")
    return _deny_decision("alert_scope_missing")


def _osint_source_scope_decision(user: UserAccount | None, source_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    bypass = _bypass_decision(user, "osint_source", source_id)
    if bypass:
        return bypass
    if source_id in _scope_values(user, SCOPE_KEYS["osint_source"]):
        return _allow_decision("osint_source_scope")
    source = get_osint_service().get_source(source_id)
    if source is None:
        return _deny_decision("osint_source_not_found")
    return _case_scope_decision(user, str(source.case_id))


def _clip_metadata(camera_id: str, clip_id: str) -> dict[str, Any] | None:
    try:
        from app.services.replay_clip_service import get_replay_clip_service

        metadata_path = get_replay_clip_service().resolve_metadata_path(camera_id, clip_id)
    except Exception:
        return None
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def can_access_camera(user, camera_id: str) -> bool:
    return _camera_scope_decision(user, camera_id).allowed


def can_access_case(user, case_id: str) -> bool:
    return _case_scope_decision(user, case_id).allowed


def can_access_evidence(user, evidence_id: str) -> bool:
    case_id = _case_for_evidence(evidence_id)
    return bool(case_id and _case_scope_decision(user, case_id).allowed)


def can_access_identity(user, identity_id: str) -> bool:
    return _identity_scope_decision(user, identity_id).allowed


def can_access_watchlist(user, watchlist_id: str) -> bool:
    return _watchlist_scope_decision(user, watchlist_id).allowed


def can_access_incident(user, incident_id: str) -> bool:
    return _incident_scope_decision(user, incident_id).allowed


def can_access_alert(user, alert_id: str) -> bool:
    return _alert_scope_decision(user, alert_id).allowed


def can_access_stream(user, camera_id: str) -> bool:
    return _camera_scope_decision(user, camera_id).allowed


def can_access_replay(user, clip_id: str, camera_id: str | None = None) -> bool:
    if not camera_id:
        return False
    return _replay_scope_decision(user, camera_id, clip_id).allowed


def can_access_osint_source(user, source_id: str) -> bool:
    return _osint_source_scope_decision(user, source_id).allowed


def can_access_analytics_scope(
    user: UserAccount | None,
    *,
    camera_id: str | None = None,
    case_id: str | None = None,
    identity_id: str | None = None,
    incident_id: str | None = None,
) -> bool:
    if camera_id and not can_access_camera(user, camera_id):
        return False
    if case_id and not can_access_case(user, case_id):
        return False
    if identity_id and not can_access_identity(user, identity_id):
        return False
    if incident_id and not can_access_incident(user, incident_id):
        return False
    return True


def can_access_event_payload(user: UserAccount | None, payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    camera_ids = list(payload.get("camera_ids", [])) or []
    if payload.get("camera_id"):
        camera_ids.append(str(payload["camera_id"]))
    if camera_ids:
        return any(can_access_camera(user, str(camera_id)) for camera_id in camera_ids)
    if payload.get("incident_id"):
        return can_access_incident(user, str(payload["incident_id"]))
    if payload.get("identity_id"):
        return can_access_identity(user, str(payload["identity_id"]))
    return False


def _replay_scope_decision(user: UserAccount | None, camera_id: str, clip_id: str) -> ObjectAccessDecision:
    if user is None:
        return _deny_decision("anonymous")
    if auth_required() is False:
        return _allow_decision("auth_disabled")
    camera_decision = _camera_scope_decision(user, camera_id)
    if not camera_decision.allowed:
        return _deny_decision("replay_camera_scope_missing")
    metadata = _clip_metadata(camera_id, clip_id)
    if metadata is None:
        return camera_decision
    metadata_camera_id = str(metadata.get("camera_id", camera_id) or camera_id)
    if metadata_camera_id != camera_id:
        return _deny_decision("replay_camera_mismatch")
    request_case_id = str((metadata.get("request") or {}).get("case_id") or metadata.get("attached_case_id") or "").strip()
    if request_case_id:
        case_decision = _case_scope_decision(user, request_case_id)
        if not case_decision.allowed:
            return _deny_decision("replay_case_scope_missing")
    return camera_decision


def _raise_denied(resource: str) -> None:
    raise HTTPException(
        status_code=403,
        detail={"status": "error", "detail": f"Access denied for {resource}"},
    )


def _resolve_request_param(request: Request, name: str) -> str:
    value = request.path_params.get(name)
    if value is None:
        value = request.query_params.get(name)
    if value is None:
        raise HTTPException(status_code=400, detail=f"Missing required parameter '{name}'")
    return str(value)


def _audit_decision(
    request: Request,
    user: UserAccount | None,
    resource_type: str,
    resource_id: str,
    decision: ObjectAccessDecision,
) -> None:
    try:
        if decision.allowed and decision.bypass:
            get_audit_log_service().record(
                "object_access_bypass",
                user=user,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=decision.reason,
                request=request,
                metadata={"role": _user_role(user)},
            )
            return
        if decision.allowed:
            return
        try:
            from inference.metrics import metrics

            metrics.increment("object_authz_denied")
        except Exception:
            pass
        get_audit_log_service().record(
            AuditAction.ACCESS_DENIED,
            user=user,
            resource_type=resource_type,
            resource_id=resource_id,
            success=False,
            detail=f"Object access denied: {decision.reason}",
            request=request,
            metadata={"reason": decision.reason},
        )
    except Exception:
        pass


def _enforce_decision(
    request: Request,
    user: UserAccount | None,
    resource_type: str,
    resource_id: str,
    decision: ObjectAccessDecision,
) -> None:
    if not auth_required():
        return
    _audit_decision(request, user, resource_type, resource_id, decision)
    if not decision.allowed:
        _raise_denied(resource_type)


def ensure_camera_access(request: Request, user: UserAccount | None, camera_id: str) -> None:
    _enforce_decision(request, user, "camera", camera_id, _camera_scope_decision(user, camera_id))


def ensure_case_access(request: Request, user: UserAccount | None, case_id: str) -> None:
    _enforce_decision(request, user, "case", case_id, _case_scope_decision(user, case_id))


def ensure_identity_access(request: Request, user: UserAccount | None, identity_id: str) -> None:
    _enforce_decision(request, user, "identity", identity_id, _identity_scope_decision(user, identity_id))


def ensure_watchlist_access(request: Request, user: UserAccount | None, watchlist_id: str) -> None:
    _enforce_decision(request, user, "watchlist", watchlist_id, _watchlist_scope_decision(user, watchlist_id))


def ensure_incident_access(request: Request, user: UserAccount | None, incident_id: str) -> None:
    _enforce_decision(request, user, "incident", incident_id, _incident_scope_decision(user, incident_id))


def ensure_alert_access(request: Request, user: UserAccount | None, alert_id: str) -> None:
    _enforce_decision(request, user, "alert", alert_id, _alert_scope_decision(user, alert_id))


def ensure_stream_access(request: Request, user: UserAccount | None, camera_id: str) -> None:
    _enforce_decision(request, user, "stream", camera_id, _camera_scope_decision(user, camera_id))


def ensure_replay_access(request: Request, user: UserAccount | None, camera_id: str, clip_id: str) -> None:
    _enforce_decision(request, user, "stream_replay", f"{camera_id}:{clip_id}", _replay_scope_decision(user, camera_id, clip_id))


def ensure_evidence_access(request: Request, user: UserAccount | None, evidence_id: str) -> None:
    case_id = _case_for_evidence(evidence_id)
    if not case_id:
        _raise_denied("evidence")
    _enforce_decision(request, user, "evidence", evidence_id, _case_scope_decision(user, case_id))


def ensure_osint_source_access(request: Request, user: UserAccount | None, source_id: str) -> None:
    _enforce_decision(request, user, "osint_source", source_id, _osint_source_scope_decision(user, source_id))


def ensure_event_payload_access(
    request: Request,
    user: UserAccount | None,
    *,
    resource_id: str,
    payload: dict[str, Any] | None,
) -> None:
    decision = _allow_decision("event_scope")
    if not can_access_event_payload(user, payload):
        decision = _deny_decision("event_scope_missing")
    _enforce_decision(request, user, "event", resource_id, decision)


def require_camera_access(camera_id_param: str = "camera_id"):
    from app.api.security_dependencies import get_current_user

    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        camera_id = _resolve_request_param(request, camera_id_param)
        ensure_camera_access(request, current_user, camera_id)
        return current_user

    return dependency


def require_case_access(case_id_param: str = "case_id"):
    from app.api.security_dependencies import get_current_user

    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        case_id = _resolve_request_param(request, case_id_param)
        ensure_case_access(request, current_user, case_id)
        return current_user

    return dependency


def require_identity_access(identity_id_param: str = "identity_id"):
    from app.api.security_dependencies import get_current_user

    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        identity_id = _resolve_request_param(request, identity_id_param)
        ensure_identity_access(request, current_user, identity_id)
        return current_user

    return dependency


def require_stream_access(camera_id_param: str = "camera_id"):
    from app.api.security_dependencies import get_current_user

    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        camera_id = _resolve_request_param(request, camera_id_param)
        ensure_stream_access(request, current_user, camera_id)
        return current_user

    return dependency


def require_evidence_access(evidence_id_param: str = "evidence_id"):
    from app.api.security_dependencies import get_current_user

    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        evidence_id = _resolve_request_param(request, evidence_id_param)
        ensure_evidence_access(request, current_user, evidence_id)
        return current_user

    return dependency
