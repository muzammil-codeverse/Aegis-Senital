import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Body, UploadFile, File, Form, HTTPException, Query, WebSocket, Request, Depends, Response
from pydantic import BaseModel
from app.api.object_authorization import (
    can_access_alert,
    can_access_camera,
    can_access_event_payload,
    can_access_identity,
    can_access_identity_candidate,
    can_access_incident,
    can_access_watchlist,
    ensure_alert_access,
    ensure_camera_access,
    ensure_event_payload_access,
    ensure_identity_access,
    ensure_identity_candidate_access,
    ensure_incident_access,
    ensure_watchlist_access,
)
from app.api.gis_routes import router as gis_router
from app.api.investigation_routes import router as investigation_router
from app.api.analytics_routes import router as analytics_router
from app.api.case_routes import router as case_router
from app.api.llm_routes import router as llm_router
from app.api.model_governance_routes import router as model_governance_router
from app.api.osint_routes import router as osint_router
from app.api.streaming_routes import router as streaming_router
from app.api.uploaded_video_routes import router as uploaded_video_router
from app.api.security_dependencies import (
    get_current_user_from_request,
    issue_csrf_token,
    require_auth as require_api_auth,
    require_permission as require_api_permission,
)
from app.api.websocket_security import authenticate_websocket
from app.core.config import load_scenario_config
from app.core.logging_config import logger
from app.services.intelligence_response_builder import IntelligenceResponseBuilder
from app.models.security_models import AuditAction, UserAccount
from app.security.config import auth_required, get_auth_config, get_rbac_config
from app.security.permissions import permissions_for_role
from app.security.upload_policy import get_upload_security_policy
from app.services.audit_log_service import get_audit_log_service
from app.services.auth_service import AuthError, AuthRateLimitError, get_auth_service
from app.services.privacy_filter import (
    filter_alert_payload,
    filter_identity_payload,
    filter_incident_payload,
    filter_watchlist_payload,
)
from app.services.user_store import get_user_store
from inference.metrics import metrics
from inference.monitoring.metrics import get_metrics

router = APIRouter()
router.include_router(gis_router)
router.include_router(investigation_router)
router.include_router(analytics_router)
router.include_router(case_router)
router.include_router(llm_router)
router.include_router(model_governance_router)
router.include_router(osint_router)
router.include_router(streaming_router)
router.include_router(uploaded_video_router)

VALID_SCENARIOS = ("security", "classroom", "traffic")


def _sensitive_headers(**extra: str) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    headers.update(extra)
    return headers


def _get_identity_db():
    from inference.identity_db import get_db

    return get_db()


def _get_intelligence_runtime():
    from inference.runtime import get_intelligence_runtime

    return get_intelligence_runtime()


def _extract_frames(video_path: str, scenario: str) -> dict:
    from app.services.video_service import extract_frames

    return extract_frames(video_path, scenario=scenario)


# ── Stream request/response models ────────────────────────────────────────────

class StreamAddRequest(BaseModel):
    source: str
    stream_id: str | None = None


class StreamRemoveRequest(BaseModel):
    stream_id: str


class AlertActionRequest(BaseModel):
    operator_id: str | None = None
    reason: str | None = None


class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    source_type: str = "mock"
    source_uri: str | None = None
    location: dict | None = None
    zone: str | None = None
    priority: str = "normal"
    enabled: bool = True
    metadata: dict | None = None


class CameraUpdateRequest(BaseModel):
    name: str | None = None
    source_type: str | None = None
    source_uri: str | None = None
    location: dict | None = None
    zone: str | None = None
    priority: str | None = None
    enabled: bool | None = None
    metadata: dict | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    role: str = "viewer"
    metadata: dict | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str
    must_change_password: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    status: str | None = None
    password: str | None = None
    metadata: dict | None = None


def _request_user(request: Request) -> UserAccount | None:
    return get_current_user_from_request(request)


def _audit(
    request: Request,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: str | None = None,
    success: bool = True,
    detail: str | None = None,
    metadata: dict | None = None,
):
    return get_audit_log_service().record(
        action,
        user=_request_user(request),
        resource_type=resource_type,
        resource_id=resource_id,
        success=success,
        detail=detail,
        request=request,
        metadata=metadata,
    )


def _role_permissions(role: str | None) -> list[str]:
    if not role:
        return []
    return permissions_for_role(role, get_rbac_config())


def _current_user_payload(user: UserAccount | None) -> dict:
    auth_cfg = get_auth_config()
    if user is None:
        return {
            "user": None,
            "permissions": [],
            "auth_required": auth_required(),
            "auth_storage_mode": "cookie" if bool(auth_cfg.get("set_auth_cookie", True)) else "bearer",
            "csrf_header_name": str(auth_cfg.get("csrf_header_name") or "X-CSRF-Token"),
        }
    return {
        "user": user.to_dict(),
        "permissions": _role_permissions(user.role),
        "auth_required": auth_required(),
        "auth_storage_mode": "cookie" if bool(auth_cfg.get("set_auth_cookie", True)) else "bearer",
        "csrf_header_name": str(auth_cfg.get("csrf_header_name") or "X-CSRF-Token"),
    }


def _filter_alert_response(payload: dict, request: Request) -> dict:
    return filter_alert_payload(payload, _request_user(request))


def _filter_incident_response(payload: dict, request: Request) -> dict:
    return filter_incident_payload(payload, _request_user(request))


def _filter_identity_response(payload: dict, request: Request) -> dict:
    return filter_identity_payload(payload, _request_user(request))


def _filter_watchlist_response(payload: dict, request: Request) -> dict:
    return filter_watchlist_payload(payload, _request_user(request))


def _deny_object_access(
    request: Request,
    resource_type: str,
    resource_id: str,
):
    try:
        metrics.increment("object_authz_denied")
    except Exception:
        pass
    _audit(
        request,
        AuditAction.ACCESS_DENIED,
        resource_type=resource_type,
        resource_id=resource_id,
        success=False,
        detail="Object-level access denied",
    )
    raise HTTPException(
        status_code=403,
        detail={"status": "error", "detail": f"Access denied for {resource_type}"},
    )


def _require_object_access(
    request: Request,
    resource_type: str,
    resource_id: str,
    allowed: bool,
) -> None:
    if not auth_required():
        return
    current_user = _request_user(request)
    if resource_type == "camera":
        ensure_camera_access(request, current_user, resource_id)
        return
    if resource_type == "identity":
        ensure_identity_access(request, current_user, resource_id)
        return
    if resource_type == "incident":
        ensure_incident_access(request, current_user, resource_id)
        return
    if resource_type == "alert":
        ensure_alert_access(request, current_user, resource_id)
        return
    if resource_type == "watchlist":
        ensure_watchlist_access(request, current_user, resource_id)
        return
    if not allowed:
        _deny_object_access(request, resource_type, resource_id)


@router.post("/api/auth/login")
def login_api(body: LoginRequest, request: Request, response: Response):
    try:
        payload = get_auth_service().login(body.username, body.password, request=request)
        auth_cfg = get_auth_config()
        if bool(auth_cfg.get("set_auth_cookie", True)):
            csrf_token = issue_csrf_token()
            response.set_cookie(
                str(auth_cfg.get("cookie_name") or "aegis_access_token"),
                payload["access_token"],
                httponly=bool(auth_cfg.get("cookie_httponly", True)),
                secure=bool(auth_cfg.get("cookie_secure", False)),
                samesite=str(auth_cfg.get("cookie_samesite") or "lax"),
                max_age=payload.get("expires_in_seconds", 0),
                path=str(auth_cfg.get("cookie_path") or "/"),
            )
            response.set_cookie(
                str(auth_cfg.get("csrf_cookie_name") or "aegis_csrf_token"),
                csrf_token,
                httponly=False,
                secure=bool(auth_cfg.get("cookie_secure", False)),
                samesite=str(auth_cfg.get("cookie_samesite") or "lax"),
                max_age=payload.get("expires_in_seconds", 0),
                path=str(auth_cfg.get("cookie_path") or "/"),
            )
            payload["csrf_token"] = csrf_token
        payload["auth_storage_mode"] = "cookie" if bool(auth_cfg.get("set_auth_cookie", True)) else "bearer"
        payload["csrf_header_name"] = str(auth_cfg.get("csrf_header_name") or "X-CSRF-Token")
        if not bool(auth_cfg.get("expose_bearer_response", True)):
            payload.pop("access_token", None)
            payload["token_type"] = "cookie"
        return payload
    except AuthRateLimitError:
        raise HTTPException(status_code=429, detail="Too many login attempts")
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/api/auth/logout")
def logout_api(
    request: Request,
    response: Response,
    current_user: UserAccount = Depends(require_api_auth),
):
    payload = get_auth_service().logout(current_user, request=request)
    auth_cfg = get_auth_config()
    cookie_path = str(auth_cfg.get("cookie_path") or "/")
    response.delete_cookie(str(auth_cfg.get("cookie_name") or "aegis_access_token"), path=cookie_path)
    response.delete_cookie(str(auth_cfg.get("csrf_cookie_name") or "aegis_csrf_token"), path=cookie_path)
    return payload


@router.get("/api/auth/me")
async def me_api(current_user: UserAccount = Depends(require_api_auth)):
    return _current_user_payload(current_user)


@router.post("/api/auth/change-password")
def change_password_api(
    body: ChangePasswordRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_auth),
):
    try:
        user = get_auth_service().change_password(
            current_user,
            body.current_password,
            body.new_password,
            request=request,
        )
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"item": user.to_dict(), "status": "ok"}


@router.get("/api/security/users")
def list_security_users_api(
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    users = get_auth_service().list_users(role=role, status=status, limit=limit)
    return {"items": [user.to_dict() for user in users], "count": len(users), "status": "ok" if users else "empty"}


@router.post("/api/security/users")
def create_security_user_api(
    body: UserCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    try:
        user = get_auth_service().create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
            metadata=body.metadata or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(
        request,
        AuditAction.USER_CREATED,
        resource_type="user",
        resource_id=user.user_id,
        metadata={"username": user.username, "role": user.role},
    )
    return {"item": user.to_dict(), "status": "ok"}


@router.get("/api/security/users/{user_id}")
def get_security_user_api(
    user_id: str,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    user = get_auth_service().get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    return {"item": user.to_dict(), "status": "ok"}


@router.patch("/api/security/users/{user_id}")
def update_security_user_api(
    user_id: str,
    body: UserUpdateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    updates = {key: value for key, value in body.model_dump().items() if value is not None}
    try:
        user = get_auth_service().update_user(user_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    _audit(
        request,
        AuditAction.USER_UPDATED,
        resource_type="user",
        resource_id=user.user_id,
        metadata={"updated_fields": sorted(updates.keys())},
    )
    return {"item": user.to_dict(), "status": "ok"}


@router.post("/api/security/users/{user_id}/disable")
def disable_security_user_api(
    user_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    user = get_auth_service().disable_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    _audit(request, AuditAction.USER_UPDATED, resource_type="user", resource_id=user.user_id, detail="User disabled")
    return {"item": user.to_dict(), "status": "ok"}


@router.post("/api/security/users/{user_id}/lock")
def lock_security_user_api(
    user_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    user = get_auth_service().lock_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    _audit(request, AuditAction.USER_UPDATED, resource_type="user", resource_id=user.user_id, detail="User locked")
    return {"item": user.to_dict(), "status": "ok"}


@router.post("/api/security/users/{user_id}/reset-password")
def reset_security_user_password_api(
    user_id: str,
    body: ResetPasswordRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("admin")),
):
    try:
        user = get_auth_service().reset_password_by_admin(
            current_user,
            user_id,
            body.new_password,
            must_change_password=body.must_change_password,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    return {"item": user.to_dict(), "status": "ok"}


@router.get("/api/security/roles")
def get_roles_api(current_user: UserAccount = Depends(require_api_auth)):
    rbac = get_rbac_config()
    if current_user.role in {"admin", "supervisor"}:
        return {"items": [{"role": role, "permissions": perms} for role, perms in rbac.items()], "status": "ok"}
    return {"items": [{"role": current_user.role, "permissions": _role_permissions(current_user.role)}], "status": "ok"}


@router.get("/api/audit/logs")
def list_audit_logs_api(
    user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start_time: float | None = Query(default=None),
    end_time: float | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    current_user: UserAccount = Depends(require_api_permission("audit:read")),
):
    items = get_audit_log_service().list_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/audit/recent")
def recent_audit_logs_api(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserAccount = Depends(require_api_permission("audit:read")),
):
    items = get_audit_log_service().get_recent(limit=limit)
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/audit/integrity")
def audit_integrity_api(
    current_user: UserAccount = Depends(require_api_permission("audit:read")),
):
    return get_audit_log_service().verify_integrity()


@router.get("/api/system/health")
def system_health_api(request: Request):
    """
    Detailed subsystem health report.

    Public callers receive filtered data (no path details).
    Authenticated admins receive full detail via include_sensitive=True.
    Increments system_health_requests metric.
    """
    from app.services.runtime_health_service import get_runtime_health_service
    from inference.monitoring.metrics import get_metrics as get_mon
    try:
        get_mon().increment("system_health_requests")
    except Exception:
        pass
    user = _request_user(request)
    include_sensitive = user is not None and getattr(user, "role", "") in {"admin", "supervisor"}
    svc = get_runtime_health_service()
    result = svc.get_health(include_sensitive=include_sensitive)
    return result


@router.get("/api/system/readiness")
def system_readiness_api():
    """
    Readiness check — returns 200 if all required subsystems are healthy,
    503 otherwise.  Suitable for load balancer / orchestrator probes.
    Increments system_readiness_failures metric on failure.
    """
    from app.services.runtime_health_service import get_runtime_health_service
    from inference.monitoring.metrics import get_metrics as get_mon
    from fastapi.responses import JSONResponse
    svc = get_runtime_health_service()
    result = svc.is_ready()
    if not result["ready"]:
        try:
            get_mon().increment("system_readiness_failures")
        except Exception:
            pass
        return JSONResponse(status_code=503, content=result)
    return result


@router.get("/api/system/liveness")
def system_liveness_api():
    """
    Liveness check — lightweight endpoint returning 200 when process is alive.
    Used by orchestrators to detect hung processes.
    """
    from app.services.runtime_health_service import get_runtime_health_service
    svc = get_runtime_health_service()
    return {"alive": svc.is_alive(), "status": "ok"}


@router.get("/health")
def health_check():
    from app.services.video_service import _engine, _runtime_db, _identity_fusion
    from app.services.identity_service import get_identity_service
    from inference.stream.stream_manager import get_stream_manager

    models_loaded = _engine is not None and getattr(_engine, "is_loaded", False)

    db_connected = False
    if _runtime_db is not None:
        try:
            db_connected = _runtime_db.db_healthy
        except Exception as exc:
            logger.warning("DB health check failed: %s", exc)

    identity_status: dict = {}
    if _identity_fusion is not None:
        try:
            identity_status = _identity_fusion.get_status()
        except Exception as exc:
            logger.warning("Identity status check failed: %s", exc)
    identity_health = get_identity_service().get_health()

    stream_health = get_stream_manager().health_summary()
    intelligence_health = _get_intelligence_runtime().get_health()

    return {
        "status": "ok",
        "models_loaded": models_loaded,
        "db_connected": db_connected,
        "identity": identity_health,
        "identity_fusion": identity_status,
        "metrics": get_metrics().snapshot(),
        "active_streams": stream_health["active_streams"],
        "total_streams": stream_health["total_streams"],
        "stream_metrics": stream_health["stream_metrics"],
        "intelligence_runtime": intelligence_health,
    }


@router.post("/process-video")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    scenario: str = Query(default="security"),
):
    content = await file.read()
    validation = get_upload_security_policy().validate(
        filename=file.filename or "upload.mp4",
        content=content,
        content_type=file.content_type,
        allowed_classes={"video"},
    )
    if scenario not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Choose from: {VALID_SCENARIOS}",
        )

    logger.info(f"Received video upload: {validation.normalized_filename} | scenario={scenario}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=validation.extension) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = _extract_frames(tmp_path, scenario=scenario)
    finally:
        os.unlink(tmp_path)

    total = sum(len(f["objects"]) for f in result["detections"])
    logger.info(
        f"Process-video complete: {result['frames']} frames, {total} detections, "
        f"{result['event_summary']['confirmed']} confirmed events"
    )
    return result


@router.get("/metrics")
def get_metrics_snapshot():
    """
    Expose all system-level pipeline metrics in a single call.

    Includes frame throughput, latency, GPU utilisation estimate, queue
    overflow counts, circuit-break events, and identity-fusion statistics.
    Intended for dashboards, Prometheus scrapers, or operator alerting.
    """
    from inference.monitoring.metrics import all_stream_snapshots
    m = get_metrics().snapshot()
    m["per_stream"] = all_stream_snapshots()
    return m


@router.get("/metrics/core")
def get_core_metrics():
    base = metrics.to_dict()
    # Phase 21: auth/user gauges from the local security store.
    try:
        counts = get_user_store().counts()
        base["users_active"] = counts.get("users_active", 0)
        base["users_locked"] = counts.get("users_locked", 0)
    except Exception:
        base.setdefault("users_active", 0)
        base.setdefault("users_locked", 0)
    # Bridge Phase-15/16 camera metrics from registry snapshot
    try:
        from app.services.camera_registry import get_camera_registry
        snap = get_camera_registry().snapshot()
        base.update({
            "registered_cameras": snap.get("total", 0),
            "active_streams": snap.get("online", 0),
            "offline_cameras": snap.get("offline", 0),
            "degraded_cameras": snap.get("degraded", 0),
        })
    except Exception:
        pass
    # Bridge stream/frame metrics from monitoring layer
    try:
        from inference.monitoring.metrics import get_metrics as get_mon
        mon = get_mon().snapshot()
        base.setdefault("stream_start_failures", mon.get("stream_start_failures", 0))
        base.setdefault("latest_frame_updates", mon.get("latest_frame_updates", 0))
        for _security_key in (
            "auth_logins_success", "auth_logins_failed", "auth_access_denied",
            "audit_events_written", "audit_write_failures", "watchlist_sensitive_reads",
            "forensic_sensitive_reads", "auth_rate_limited", "websocket_auth_success",
            "websocket_auth_failed", "password_changes", "password_reset_by_admin",
            "audit_integrity_checks", "audit_integrity_failures", "object_authz_denied",
            "mfa_challenges_created", "mfa_challenges_failed",
        ):
            base.setdefault(_security_key, mon.get(_security_key, 0))
    except Exception:
        pass
    # Bridge MJPEG metrics from core metrics
    base.setdefault("active_mjpeg_clients", metrics.active_mjpeg_clients if hasattr(metrics, "active_mjpeg_clients") else 0)
    base.setdefault("mjpeg_frames_served", metrics.mjpeg_frames_served if hasattr(metrics, "mjpeg_frames_served") else 0)
    base.setdefault("stale_camera_frames", metrics.stale_camera_frames if hasattr(metrics, "stale_camera_frames") else 0)
    # Bridge Phase-18 geospatial metrics
    for _geo_key in ("map_state_requests", "map_zone_queries", "map_topology_queries",
                     "geofence_checks", "map_incident_markers", "map_alert_markers"):
        base.setdefault(_geo_key, getattr(metrics, _geo_key, 0))
    # Bridge Phase-19 handoff metrics
    for _ho_key in ("handoff_predictions_created", "handoff_candidates_observed",
                    "handoffs_confirmed", "handoffs_rejected", "handoffs_expired",
                    "active_handoffs", "websocket_handoff_clients",
                    "websocket_handoff_messages", "websocket_handoff_dropped_messages"):
        base.setdefault(_ho_key, getattr(metrics, _ho_key, 0))
    # Live active_handoffs count from store
    try:
        base["active_handoffs"] = _get_intelligence_runtime().handoff_store.active_count()
    except Exception:
        pass
    # Bridge Phase-24 deployment foundation metrics
    try:
        from inference.monitoring.metrics import get_metrics as _get_mon24
        _mon24 = _get_mon24().snapshot()
        for _p24_key in (
            "system_health_requests", "system_readiness_failures", "runtime_validation_failures",
            "open_vocab_model_load_attempts", "open_vocab_model_load_success",
            "open_vocab_model_load_failures", "open_vocab_model_unloads",
            "open_vocab_model_auto_load_attempts_total",
            "open_vocab_model_auto_load_failures_total",
            "open_vocab_model_auto_load_success_total",
            "open_vocab_model_auto_load_skipped_total",
            "open_vocab_model_auto_load_timeout_total",
            "segmentation_requests_total",
            "segmentation_success_total",
            "segmentation_failures_total",
            "segmentation_skipped_total",
            "segmentation_latency_ms",
            "segmentation_masks_generated_total",
            "segmentation_mask_area_ratio",
            "segmentation_provider_unavailable_total",
        ):
            base.setdefault(_p24_key, _mon24.get(_p24_key, 0))
    except Exception:
        for _p24_key in (
            "system_health_requests", "system_readiness_failures", "runtime_validation_failures",
            "open_vocab_model_load_attempts", "open_vocab_model_load_success",
            "open_vocab_model_load_failures", "open_vocab_model_unloads",
            "open_vocab_model_auto_load_attempts_total",
            "open_vocab_model_auto_load_failures_total",
            "open_vocab_model_auto_load_success_total",
            "open_vocab_model_auto_load_skipped_total",
            "open_vocab_model_auto_load_timeout_total",
            "segmentation_requests_total",
            "segmentation_success_total",
            "segmentation_failures_total",
            "segmentation_skipped_total",
            "segmentation_latency_ms",
            "segmentation_masks_generated_total",
            "segmentation_mask_area_ratio",
            "segmentation_provider_unavailable_total",
        ):
            base.setdefault(_p24_key, 0)
    return base


@router.get("/config/{scenario}")
def get_config(scenario: str):
    logger.info(f"Config requested: {scenario}")
    try:
        config = load_scenario_config(scenario)
        return config
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario}' not found")


@router.get("/events")
def list_events(request: Request):
    logger.info("Events list requested")
    user = _request_user(request)
    events = [event for event in _get_identity_db().get_events(limit=50) if can_access_event_payload(user, event)]
    return [
        {
            "id": e.get("event_id"),
            "timestamp": e.get("timestamp"),
            "type": e.get("event_type"),
            "severity": e.get("severity"),
            "confidence": e.get("confidence"),
            "metadata": e.get("metadata", {}),
        }
        for e in events
    ]


@router.get("/detections")
def list_detections(request: Request):
    logger.info("Detections list requested")
    user = _request_user(request)
    tracks = [track for track in _get_identity_db().get_tracks(limit=50) if can_access_event_payload(user, track)]
    return [
        {
            "id": t.get("track_id"),
            "timestamp": t.get("last_seen"),
            "type": t.get("class_name"),
            "confidence": t.get("confidence"),
            "bbox": t.get("bbox", []),
            "metadata": t.get("metadata", {}),
        }
        for t in tracks
    ]


# ── Stream management endpoints ───────────────────────────────────────────────

@router.get("/streams")
def list_streams():
    """Return status and per-stream metrics for all registered streams."""
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Streams list requested")
    return get_stream_manager().list_streams()


@router.post("/streams/add")
def add_stream(body: StreamAddRequest, request: Request):
    """
    Register and start a new stream.

    ``source`` may be an RTSP URL, a local camera index (as a string,
    e.g. ``"0"``), or a video file path.
    ``stream_id`` is optional — one is auto-generated when omitted.
    """
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Add stream requested: source=%s stream_id=%s", body.source, body.stream_id)
    try:
        assigned_id = get_stream_manager().add_stream(
            source=body.source,
            stream_id=body.stream_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=assigned_id, detail="Stream added")
    return {"stream_id": assigned_id, "status": "started"}


@router.post("/streams/remove")
def remove_stream(body: StreamRemoveRequest, request: Request):
    """Stop and deregister a stream by its stream_id."""
    from inference.stream.stream_manager import get_stream_manager
    logger.info("Remove stream requested: stream_id=%s", body.stream_id)
    removed = get_stream_manager().remove_stream(body.stream_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Stream '{body.stream_id}' not found",
        )
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=body.stream_id, detail="Stream removed")
    return {"stream_id": body.stream_id, "status": "stopped"}


@router.get("/api/incidents")
@router.get("/incidents")
def list_incidents_api(request: Request):
    user = _request_user(request)
    incidents = [
        incident
        for incident in _get_intelligence_runtime().get_incidents()
        if can_access_incident(user, str(incident.get("incident_id") or incident.get("id") or ""))
        or can_access_event_payload(user, incident)
    ]
    return _filter_incident_response(IntelligenceResponseBuilder.incident_feed(incidents), request)


@router.get("/api/incidents/{incident_id}")
@router.get("/incidents/{incident_id}")
def get_incident_api(incident_id: str, request: Request):
    _require_object_access(request, "incident", incident_id, can_access_incident(_request_user(request), incident_id))
    runtime = _get_intelligence_runtime()
    incident = runtime.incident_engine.get_incident(incident_id)
    _audit(request, AuditAction.INCIDENT_VIEWED, resource_type="incident", resource_id=incident_id)
    return _filter_incident_response(IntelligenceResponseBuilder.incident_detail(incident), request)


@router.get("/api/timeline/{track_id}")
@router.get("/timeline/{track_id}")
def get_timeline(track_id: str, request: Request):
    events = _get_intelligence_runtime().get_track_timeline(track_id)
    visible_events = [event for event in events if can_access_event_payload(_request_user(request), event)]
    if events and not visible_events:
        _deny_object_access(request, "event", track_id)
    try:
        metrics.increment("forensic_sensitive_reads")
    except Exception:
        pass
    _audit(request, AuditAction.FORENSIC_REPLAY_VIEWED, resource_type="track", resource_id=track_id)
    return _filter_incident_response(IntelligenceResponseBuilder.timeline(track_id, visible_events), request)


@router.get("/api/anomalies/live")
@router.get("/anomalies/live")
def get_live_anomalies(request: Request):
    user = _request_user(request)
    anomalies = [item for item in _get_intelligence_runtime().get_live_anomalies() if can_access_event_payload(user, item)]
    return IntelligenceResponseBuilder.anomalies(anomalies)


@router.get("/api/alerts")
def list_alerts_api(
    request: Request,
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    user = _request_user(request)
    response = _get_intelligence_runtime().get_alerts(state=state, severity=severity, limit=limit)
    response["items"] = [
        item
        for item in response["items"]
        if can_access_alert(user, str(item.get("alert_id") or ""))
        or can_access_event_payload(user, item)
    ]
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_feed_payload(response["items"]), request)


@router.get("/api/alerts/live")
def live_alerts_api(request: Request, limit: int = Query(default=100, ge=1, le=1000)):
    response = _get_intelligence_runtime().get_live_alert_feed(limit=limit)
    user = _request_user(request)
    response["items"] = [
        item
        for item in response["items"]
        if can_access_alert(user, str(item.get("alert_id") or ""))
        or can_access_event_payload(user, item)
    ]
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_feed_payload(response["items"]), request)


@router.get("/api/alerts/operator-queue")
def operator_queue_api(request: Request, limit: int = Query(default=100, ge=1, le=1000)):
    response = _get_intelligence_runtime().get_live_alert_feed(limit=limit)
    user = _request_user(request)
    response["items"] = [
        item
        for item in response["items"]
        if can_access_alert(user, str(item.get("alert_id") or ""))
        or can_access_event_payload(user, item)
    ]
    return _filter_alert_response(IntelligenceResponseBuilder.build_operator_queue_payload(response["items"]), request)


@router.get("/api/alerts/{alert_id}")
def get_alert_api(alert_id: str, request: Request):
    _require_object_access(request, "alert", alert_id, can_access_alert(_request_user(request), alert_id))
    response = _get_intelligence_runtime().get_alert(alert_id)
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_detail_payload(response["item"]), request)


@router.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert_api(alert_id: str, request: Request, body: AlertActionRequest | None = None):
    ensure_alert_access(request, _request_user(request), alert_id)
    operator_id = body.operator_id if body else None
    response = _get_intelligence_runtime().acknowledge_alert(alert_id, operator_id=operator_id)
    _audit(request, AuditAction.ALERT_ACKNOWLEDGED, resource_type="alert", resource_id=alert_id)
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_detail_payload(response["item"]), request)


@router.post("/api/alerts/{alert_id}/resolve")
def resolve_alert_api(alert_id: str, request: Request, body: AlertActionRequest | None = None):
    ensure_alert_access(request, _request_user(request), alert_id)
    operator_id = body.operator_id if body else None
    response = _get_intelligence_runtime().resolve_alert(alert_id, operator_id=operator_id)
    _audit(request, AuditAction.ALERT_RESOLVED, resource_type="alert", resource_id=alert_id)
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_detail_payload(response["item"]), request)


@router.post("/api/alerts/{alert_id}/escalate")
def escalate_alert_api(alert_id: str, request: Request, body: AlertActionRequest | None = None):
    ensure_alert_access(request, _request_user(request), alert_id)
    reason = body.reason if body else None
    response = _get_intelligence_runtime().escalate_alert(alert_id, reason=reason)
    _audit(
        request,
        AuditAction.ALERT_ESCALATED,
        resource_type="alert",
        resource_id=alert_id,
        detail="Alert escalated",
    )
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_detail_payload(response["item"]), request)


@router.get("/api/alerts/{alert_id}/history")
def alert_history_api(alert_id: str, request: Request):
    ensure_alert_access(request, _request_user(request), alert_id)
    response = _get_intelligence_runtime().get_alert_history(alert_id)
    response["items"] = [
        item
        for item in response["items"]
        if can_access_alert(_request_user(request), str(item.get("alert_id") or alert_id))
        or can_access_event_payload(_request_user(request), item)
    ]
    return _filter_alert_response(IntelligenceResponseBuilder.build_alert_history_payload(response["items"]), request)


# ── Camera registry endpoints ─────────────────────────────────────────────────

@router.get("/api/cameras")
def list_cameras_api(
    request: Request,
    status: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
):
    from app.services.camera_registry import get_camera_registry
    enabled_filter = enabled
    cameras = [
        camera
        for camera in get_camera_registry().list_cameras(status=status, enabled=enabled_filter)
        if can_access_camera(_request_user(request), camera.camera_id)
    ]
    items = [c.to_dict() for c in cameras]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.post("/api/cameras")
def create_camera_api(body: CameraCreateRequest, request: Request):
    from app.services.camera_registry import get_camera_registry
    try:
        camera = get_camera_registry().register_camera(body.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=507, detail=str(exc))
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera.camera_id, detail="Camera registered")
    return {"item": camera.to_dict(), "status": "ok"}


@router.get("/api/cameras/latest-frames")
def list_latest_frames_api(request: Request):
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    items = [
        item
        for item in get_frame_snapshot_service().list_latest_frames()
        if can_access_camera(_request_user(request), str(item.get("camera_id") or ""))
    ]
    return _filter_incident_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)


@router.get("/api/cameras/{camera_id}/status")
def get_camera_status_api(camera_id: str, request: Request):
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    from app.services.camera_registry import get_camera_registry
    from app.services.stream_session_manager import get_stream_session_manager
    camera = get_camera_registry().get_camera(camera_id)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    stream_state = get_stream_session_manager().get_stream_state(camera_id)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="camera", resource_id=camera_id)
    return {"item": {**camera.to_dict(), "stream_session": stream_state}, "status": "ok"}


@router.get("/api/cameras/{camera_id}/latest-frame")
def get_camera_latest_frame_api(camera_id: str, request: Request):
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    status = frame.get("status", "ok")
    return _filter_incident_response({"item": frame, "status": status}, request)


@router.get("/api/cameras/{camera_id}/latest-frame/image")
def get_camera_latest_frame_image(camera_id: str, request: Request):
    """Serve the latest annotated frame image with path-traversal protection."""
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    from fastapi.responses import FileResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    if frame.get("status") == "no_frame" or not frame.get("frame_path"):
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No latest frame available"},
        )

    resolved = safe_frame_path(frame["frame_path"])
    if resolved is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "Frame file unavailable"},
        )
    if not is_safe_extension(resolved):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Unsupported frame file type"},
        )

    media_type = "image/png" if resolved.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(resolved), media_type=media_type, headers=_sensitive_headers())


@router.get("/api/cameras/{camera_id}/latest-frame/annotated-image")
def get_camera_latest_frame_annotated_image(camera_id: str, request: Request):
    """Serve the latest annotated (bounding-box rendered) frame image."""
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    from fastapi.responses import FileResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    frame = get_frame_snapshot_service().get_latest_frame(camera_id)
    if frame.get("status") == "no_frame":
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No latest frame available"},
        )

    # Prefer annotated frame; fall back to raw frame
    ann_path = frame.get("annotated_frame_path")
    raw_path = frame.get("frame_path")
    chosen_path = ann_path or raw_path
    if not chosen_path:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "No frame file available"},
        )

    resolved = safe_frame_path(chosen_path)
    if resolved is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "detail": "Frame file unavailable"},
        )
    if not is_safe_extension(resolved):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "detail": "Unsupported frame file type"},
        )
    media_type = "image/png" if resolved.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(resolved), media_type=media_type, headers=_sensitive_headers())


@router.get("/api/cameras/{camera_id}/mjpeg")
async def camera_mjpeg_stream(camera_id: str, request: Request):
    """Lightweight MJPEG stream using latest frame snapshots (annotated preferred)."""
    import asyncio
    from fastapi.responses import StreamingResponse, JSONResponse
    from app.services.frame_snapshot_service import get_frame_snapshot_service
    from app.core.security import safe_frame_path, is_safe_extension

    ensure_camera_access(request, _request_user(request), camera_id)

    # Load streaming config
    try:
        from inference.config_runtime import load_runtime_config
        cfg = load_runtime_config("camera_streaming")
        mjpeg_cfg = cfg.get("mjpeg", {})
        enabled = bool(mjpeg_cfg.get("enabled", True))
        fps = float(mjpeg_cfg.get("fps", 2))
        max_clients = int(mjpeg_cfg.get("max_clients", 16))
        stale_seconds = float(mjpeg_cfg.get("stale_frame_seconds", 10))
    except Exception:
        enabled, fps, max_clients, stale_seconds = True, 2.0, 16, 10.0

    if not enabled:
        return JSONResponse(
            status_code=503,
            content={"status": "disabled", "detail": "MJPEG streaming is disabled"},
        )

    # Check client limit
    current = getattr(metrics, "active_mjpeg_clients", 0)
    if current >= max_clients:
        return JSONResponse(
            status_code=503,
            content={"status": "capacity", "detail": "MJPEG max client limit reached"},
        )

    snapshot_svc = get_frame_snapshot_service()
    interval = max(0.05, 1.0 / fps)
    boundary = b"--aegisframe"

    metrics.increment("active_mjpeg_clients")

    async def generate():
        try:
            while True:
                frame_meta = snapshot_svc.get_latest_frame(camera_id)
                # 17D: prefer annotated frame path when available
                frame_path = frame_meta.get("annotated_frame_path") or frame_meta.get("frame_path")
                age = frame_meta.get("age_seconds")

                img_bytes: bytes | None = None
                if frame_path and (age is None or age <= stale_seconds):
                    resolved = safe_frame_path(frame_path)
                    if resolved is not None and is_safe_extension(resolved):
                        try:
                            with open(str(resolved), "rb") as fh:
                                img_bytes = fh.read()
                        except OSError:
                            img_bytes = None

                if img_bytes:
                    metrics.increment("mjpeg_frames_served")
                    header = (
                        boundary + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(img_bytes)).encode() + b"\r\n"
                        b"\r\n"
                    )
                    yield header + img_bytes + b"\r\n"
                else:
                    # Heartbeat boundary keeps connection alive
                    metrics.increment("stale_camera_frames")
                    yield boundary + b"\r\n\r\n"

                await asyncio.sleep(interval)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            metrics.increment("mjpeg_client_disconnects")
            with metrics._lock:
                metrics.active_mjpeg_clients = max(0, metrics.active_mjpeg_clients - 1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=aegisframe",
        headers=_sensitive_headers(**{"X-Accel-Buffering": "no"}),
    )


@router.get("/api/cameras/{camera_id}/timeline")
def get_camera_timeline_api(
    camera_id: str,
    request: Request,
    start_time: float | None = Query(default=None),
    end_time: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent timeline entries for a camera, optionally bounded by time range."""
    ensure_camera_access(request, _request_user(request), camera_id)
    import time as _time
    try:
        from inference.metrics import metrics as core_metrics
        core_metrics.increment("camera_timeline_queries")
    except Exception:
        pass

    try:
        from inference.forensics.timeline_store import TimelineStore
        store = TimelineStore()
        rows = store.recent(limit=500)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Timeline store unavailable: {exc}")

    filtered = [r for r in rows if r.get("camera_id") == camera_id]
    if start_time is not None:
        filtered = [r for r in filtered if (r.get("timestamp") or 0) >= start_time]
    if end_time is not None:
        filtered = [r for r in filtered if (r.get("timestamp") or 0) <= end_time]
    filtered.sort(key=lambda r: r.get("timestamp", 0))
    items = filtered[-limit:]
    try:
        metrics.increment("forensic_sensitive_reads")
    except Exception:
        pass
    _audit(request, AuditAction.FORENSIC_REPLAY_VIEWED, resource_type="camera", resource_id=camera_id)
    return _filter_incident_response({"items": items, "count": len(items), "camera_id": camera_id, "status": "ok"}, request)


@router.get("/api/incidents/{incident_id}/replay")
def get_incident_replay_api(incident_id: str, request: Request):
    """Return a replay manifest for an incident: frames, events, alerts, and timeline."""
    _require_object_access(request, "incident", incident_id, can_access_incident(_request_user(request), incident_id))
    try:
        from inference.metrics import metrics as core_metrics
        core_metrics.increment("incident_replay_queries")
    except Exception:
        pass

    # Load config
    try:
        from inference.config_runtime import load_runtime_config
        rcfg = load_runtime_config("forensic_console").get("incident_replay", {})
        max_frames = int(rcfg.get("max_frames", 500))
        include_alerts = bool(rcfg.get("include_alerts", True))
        include_events = bool(rcfg.get("include_events", True))
        include_timeline = bool(rcfg.get("include_timeline", True))
    except Exception:
        max_frames, include_alerts, include_events, include_timeline = 500, True, True, True

    runtime = _get_intelligence_runtime()

    # Resolve incident
    incident = None
    try:
        incident = runtime.incident_engine.get_incident(incident_id)
    except Exception:
        pass
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    inc_dict = incident if isinstance(incident, dict) else (incident.to_dict() if hasattr(incident, "to_dict") else vars(incident))

    # Gather timeline entries containing this incident's track ids
    frames: list[dict] = []
    if include_timeline:
        try:
            from inference.forensics.timeline_store import TimelineStore
            store = TimelineStore()
            all_rows = store.recent(limit=max_frames * 2)
            frames = [
                r for r in all_rows
                if incident_id in (r.get("incident_ids") or [])
            ][:max_frames]
        except Exception:
            pass

    # Gather related alerts
    alert_items: list[dict] = []
    if include_alerts:
        try:
            resp = runtime.get_alerts(limit=200)
            alert_items = [
                a for a in (resp.get("items") or [])
                if incident_id in (a.get("incident_ids") or [])
                or a.get("incident_id") == incident_id
            ]
        except Exception:
            pass

    try:
        metrics.increment("forensic_sensitive_reads")
    except Exception:
        pass
    _audit(request, AuditAction.FORENSIC_REPLAY_VIEWED, resource_type="incident", resource_id=incident_id)
    return _filter_incident_response({
        "incident_id": incident_id,
        "incident": inc_dict,
        "frames": frames,
        "alerts": alert_items,
        "frame_count": len(frames),
        "alert_count": len(alert_items),
        "status": "ok",
    }, request)


@router.websocket("/ws/frames")
async def websocket_frames_endpoint(websocket: WebSocket):
    """Real-time frame-update WebSocket stream for all cameras."""
    from app.services.websocket_frame_service import get_websocket_frame_service
    user = await authenticate_websocket(websocket, required_permission="camera:read")
    if user is None:
        return
    await get_websocket_frame_service().handle_connection(websocket, user=user)


@router.get("/api/cameras/{camera_id}/heatmap")
@router.get("/cameras/{camera_id}/heatmap")
def get_camera_heatmap(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    heatmap = _get_intelligence_runtime().get_camera_heatmap(camera_id)
    return IntelligenceResponseBuilder.heatmap(heatmap, camera_id)


@router.get("/api/cameras/{camera_id}")
def get_camera_api(camera_id: str, request: Request):
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    from app.services.camera_registry import get_camera_registry
    camera = get_camera_registry().get_camera(camera_id)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="camera", resource_id=camera_id)
    return {"item": camera.to_dict(), "status": "ok"}


@router.patch("/api/cameras/{camera_id}")
def update_camera_api(camera_id: str, body: CameraUpdateRequest, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.camera_registry import get_camera_registry
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    camera = get_camera_registry().update_camera(camera_id, updates)
    if camera is None:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, metadata={"updated_fields": sorted(updates.keys())})
    return {"item": camera.to_dict(), "status": "ok"}


@router.delete("/api/cameras/{camera_id}")
def delete_camera_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.camera_registry import get_camera_registry
    removed = get_camera_registry().remove_camera(camera_id)
    if not removed:
        return {"item": None, "status": "not_found", "detail": f"Camera '{camera_id}' not found"}
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Camera removed")
    return {"item": None, "status": "ok", "detail": f"Camera '{camera_id}' removed"}


# ── Stream session control endpoints ─────────────────────────────────────────

@router.post("/api/cameras/{camera_id}/start")
def start_camera_stream_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().start_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Stream start requested")
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/stop")
def stop_camera_stream_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().stop_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Stream stop requested")
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/pause")
def pause_camera_stream_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().pause_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Stream pause requested")
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/resume")
def resume_camera_stream_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().resume_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Stream resume requested")
    return {"item": result, "status": "ok"}


@router.post("/api/cameras/{camera_id}/restart")
def restart_camera_stream_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    result = get_stream_session_manager().restart_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="camera", resource_id=camera_id, detail="Stream restart requested")
    return {"item": result, "status": "ok"}


# ── Stream session list endpoints ─────────────────────────────────────────────

@router.get("/api/streams")
def list_stream_sessions_api(request: Request):
    from app.services.stream_session_manager import get_stream_session_manager
    items = [
        item
        for item in get_stream_session_manager().list_stream_states()
        if can_access_camera(_request_user(request), str(item.get("camera_id") or ""))
    ]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/streams/{camera_id}")
def get_stream_session_api(camera_id: str, request: Request):
    ensure_camera_access(request, _request_user(request), camera_id)
    from app.services.stream_session_manager import get_stream_session_manager
    item = get_stream_session_manager().get_stream_state(camera_id)
    return {"item": item, "status": "ok"}


# ── Geospatial / Map endpoints ────────────────────────────────────────────────

def _geo():
    from app.services.geospatial_service import get_geospatial_service
    return get_geospatial_service()


def _geo_metric(name: str) -> None:
    try:
        metrics.increment(name)
    except Exception:
        pass


def _map_camera_visible(user: UserAccount | None, camera_id: str | None) -> bool:
    value = str(camera_id or "").strip()
    return bool(value) and can_access_camera(user, value)


def _filter_map_cameras(user: UserAccount | None, items: list[dict]) -> list[dict]:
    return [item for item in items if _map_camera_visible(user, item.get("camera_id"))]


def _filter_map_connections(user: UserAccount | None, items: list[dict]) -> list[dict]:
    return [
        item
        for item in items
        if _map_camera_visible(user, item.get("from_camera")) and _map_camera_visible(user, item.get("to_camera"))
    ]


def _filter_map_handoffs(user: UserAccount | None, items: list[dict]) -> list[dict]:
    return [
        item
        for item in items
        if can_access_camera(user, str(item.get("source_camera") or ""))
        or can_access_camera(user, str(item.get("target_camera") or ""))
        or can_access_identity(user, str(item.get("identity_id") or ""))
    ]


@router.get("/api/map/state")
def get_map_state_api(request: Request):
    _geo_metric("map_state_requests")
    user = _request_user(request)
    state = _geo().get_map_state()
    state["cameras"] = _filter_map_cameras(user, list(state.get("cameras") or []))
    state["connections"] = _filter_map_connections(user, list(state.get("connections") or []))
    state["incidents"] = [
        item
        for item in list(state.get("incidents") or [])
        if can_access_incident(user, str(item.get("incident_id") or ""))
        or can_access_camera(user, str(item.get("camera_id") or ""))
    ]
    state["alerts"] = [
        item
        for item in list(state.get("alerts") or [])
        if can_access_alert(user, str(item.get("alert_id") or ""))
        or can_access_camera(user, str(item.get("camera_id") or ""))
    ]
    _geo_metric("map_incident_markers")
    _geo_metric("map_alert_markers")
    # Attach active handoffs to map state
    try:
        handoffs = _get_intelligence_runtime().handoff_store.list_active(limit=100)
        state["handoffs"] = _filter_map_handoffs(user, handoffs)
    except Exception:
        state["handoffs"] = []
    _audit(request, AuditAction.MAP_VIEWED, resource_type="map", resource_id="state")
    return {"item": state, "status": "ok"}


@router.get("/api/map/sites")
def list_map_sites_api():
    items = _geo().list_sites()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/sites/{site_id}")
def get_map_site_api(site_id: str):
    site = _geo().get_site(site_id)
    if site is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    return {"item": site, "status": "ok"}


@router.get("/api/map/zones")
def list_map_zones_api(site_id: str | None = Query(default=None)):
    _geo_metric("map_zone_queries")
    items = _geo().list_zones(site_id=site_id)
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/zones/{zone_id}")
def get_map_zone_api(zone_id: str):
    _geo_metric("map_zone_queries")
    zone = _geo().get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    return {"item": zone, "status": "ok"}


@router.get("/api/map/geofences")
def list_map_geofences_api():
    items = _geo().list_geofences()
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/cameras")
def list_map_cameras_api(request: Request):
    items = _filter_map_cameras(_request_user(request), _geo().get_camera_nodes())
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/connections")
def list_map_connections_api(request: Request):
    items = _filter_map_connections(_request_user(request), _geo().get_camera_connections())
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/incidents")
def list_map_incidents_api(request: Request):
    _geo_metric("map_incident_markers")
    user = _request_user(request)
    items = [
        item
        for item in _geo().get_incident_markers()
        if can_access_incident(user, str(item.get("incident_id") or ""))
        or can_access_camera(user, str(item.get("camera_id") or ""))
    ]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/alerts")
def list_map_alerts_api(request: Request):
    _geo_metric("map_alert_markers")
    user = _request_user(request)
    items = [
        item
        for item in _geo().get_alert_markers()
        if can_access_alert(user, str(item.get("alert_id") or ""))
        or can_access_camera(user, str(item.get("camera_id") or ""))
    ]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/map/topology")
def get_map_topology_api(request: Request):
    _geo_metric("map_topology_queries")
    topology = _geo().get_camera_topology()
    user = _request_user(request)
    topology["cameras"] = _filter_map_cameras(user, list(topology.get("cameras") or []))
    topology["connections"] = _filter_map_connections(user, list(topology.get("connections") or []))
    visible_camera_ids = {str(item.get("camera_id") or "") for item in topology["cameras"]}
    topology["adjacency"] = {
        camera_id: [peer for peer in peers if peer in visible_camera_ids]
        for camera_id, peers in dict(topology.get("adjacency") or {}).items()
        if camera_id in visible_camera_ids
    }
    return {"item": topology, "status": "ok"}


# ── Handoff endpoints ─────────────────────────────────────────────────────────

def _handoff_store():
    return _get_intelligence_runtime().handoff_store


@router.get("/api/handoffs/active")
def list_active_handoffs_api(request: Request, limit: int = Query(default=100, ge=1, le=500)):
    try:
        metrics.increment("active_handoffs")
    except Exception:
        pass
    user = _request_user(request)
    items = [
        item
        for item in _handoff_store().list_active(limit=limit)
        if can_access_camera(user, str(item.get("source_camera") or ""))
        or can_access_camera(user, str(item.get("target_camera") or ""))
        or can_access_identity(user, str(item.get("identity_id") or ""))
    ]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/handoffs/recent")
def list_recent_handoffs_api(request: Request, limit: int = Query(default=100, ge=1, le=500)):
    user = _request_user(request)
    items = [
        item
        for item in _handoff_store().list_recent(limit=limit)
        if can_access_camera(user, str(item.get("source_camera") or ""))
        or can_access_camera(user, str(item.get("target_camera") or ""))
        or can_access_identity(user, str(item.get("identity_id") or ""))
    ]
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/handoffs/identity/{identity_id}")
def list_handoffs_by_identity_api(identity_id: str, request: Request, limit: int = Query(default=100, ge=1, le=500)):
    ensure_identity_access(request, _request_user(request), identity_id)
    items = _handoff_store().list_by_identity(identity_id, limit=limit)
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/handoffs/camera/{camera_id}")
def list_handoffs_by_camera_api(camera_id: str, request: Request, limit: int = Query(default=100, ge=1, le=500)):
    _require_object_access(request, "camera", camera_id, can_access_camera(_request_user(request), camera_id))
    items = _handoff_store().list_by_camera(camera_id, limit=limit)
    return {"items": items, "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/handoffs/{handoff_id}")
def get_handoff_api(handoff_id: str, request: Request):
    item = _handoff_store().get_handoff(handoff_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Handoff '{handoff_id}' not found")
    if not (
        can_access_camera(_request_user(request), str(item.get("source_camera") or ""))
        or can_access_camera(_request_user(request), str(item.get("target_camera") or ""))
        or can_access_identity(_request_user(request), str(item.get("identity_id") or ""))
    ):
        _deny_object_access(request, "handoff", handoff_id)
    return {"item": item, "status": "ok"}


@router.websocket("/ws/handoffs")
async def websocket_handoffs_endpoint(websocket: WebSocket):
    """Real-time cross-camera handoff event stream."""
    from app.services.websocket_handoff_service import get_websocket_handoff_service
    user = await authenticate_websocket(websocket, required_permission=("camera:read", "incident:read"))
    if user is None:
        return
    await get_websocket_handoff_service().handle_connection(websocket, user=user)


@router.websocket("/ws/open-vocab")
async def websocket_open_vocab_endpoint(websocket: WebSocket):
    """
    Phase 25 — Real-time Open-Vocab scan result stream.

    Receives OPEN_VOCAB_SCAN_RESULT events from the event bus and pushes
    normalized scan payloads (no raw frames, no embeddings) to subscribers.
    Rate-limited per camera.  Falls back to REST polling if disconnected.
    """
    from app.services.websocket_open_vocab_service import get_websocket_open_vocab_service
    user = await authenticate_websocket(websocket, required_permission="open_vocab:read")
    if user is None:
        return
    await get_websocket_open_vocab_service().connect(websocket, user=user)


# ============================================================
# MODEL REGISTRY ENDPOINTS (Phase 20)
# ============================================================

def _get_model_registry():
    from ml.runtime.model_registry import get_model_registry
    return get_model_registry()


@router.get("/api/models")
def list_models_api(
    task: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
):
    """List all models in the registry, optionally filtered by task or enabled state."""
    try:
        registry = _get_model_registry()
        items = registry.list_models(task=task, enabled_only=enabled_only)
        return {"items": items, "count": len(items), "status": "ok" if items else "empty"}
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/models/health")
def get_models_health_api():
    """Return health and inference stats for all registered models."""
    try:
        registry = _get_model_registry()
        items = registry.list_models()
        health_summary = [
            {
                "model_id": m["model_id"],
                "health": m["health"],
                "inference": m["inference"],
            }
            for m in items
        ]
        return {"items": health_summary, "count": len(health_summary), "status": "ok"}
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.post("/api/models/reload")
def reload_models_api(request: Request):
    """Force-reload the model registry from disk."""
    try:
        registry = _get_model_registry()
        registry.reload()
        items = registry.list_models()
        _audit(request, AuditAction.MODEL_UPDATED, resource_type="model_registry", resource_id="registry", detail="Registry reloaded")
        return {"status": "ok", "count": len(items), "detail": "Registry reloaded"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.patch("/api/models/{model_id:path}")
async def patch_model_api(model_id: str, payload: dict, request: Request):
    """Patch allowed runtime fields (enabled, confidence_threshold, device_preference)."""
    try:
        registry = _get_model_registry()
        allowed = {
            k: v
            for k, v in payload.items()
            if k in {"enabled", "confidence_threshold", "device_preference"}
        }
        ok = registry.patch_model(model_id, allowed)
        if not ok:
            return {"status": "not_found", "detail": f"Model {model_id} not found"}
        item = registry.get_model(model_id)
        _audit(request, AuditAction.MODEL_UPDATED, resource_type="model", resource_id=model_id, metadata={"updated_fields": sorted(allowed.keys())})
        return {"status": "ok", "item": item}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/api/models/{model_id:path}")
def get_model_api(model_id: str):
    """Retrieve a single model record by ID."""
    try:
        registry = _get_model_registry()
        item = registry.get_model(model_id)
        if item is None:
            return {
                "item": None,
                "status": "not_found",
                "detail": f"Model {model_id} not found",
            }
        return {"item": item, "status": "ok", "detail": None}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


# ============================================================
# IDENTITY PROFILE ENDPOINTS (Phase 20)
# ============================================================

def _id_store():
    from inference.identity.identity_profile_store import get_identity_store
    return get_identity_store()


def _wl_store():
    from inference.identity.watchlist_store import get_watchlist_store
    return get_watchlist_store()


def _identity_service():
    from app.services.identity_service import get_identity_service
    return get_identity_service()


@router.get("/api/identity/health")
def get_identity_health_api(request: Request):
    try:
        return _filter_identity_response({"item": _identity_service().get_health(), "status": "ok"}, request)
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.get("/api/identity/candidates")
def list_identity_candidates_api(
    request: Request,
    review_status: Optional[str] = Query(default=None),
    current_user: UserAccount = Depends(require_api_permission("identity:read")),
):
    from app.services.identity_candidate_service import explainability_payload, get_identity_candidate_service

    try:
        rows = get_identity_candidate_service().list_candidates(review_status=review_status)
        items = []
        for row in rows:
            if not can_access_identity_candidate(current_user, row):
                continue
            items.append({**row, "explainability": explainability_payload(row)})
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/identity/candidates/{candidate_id}")
def get_identity_candidate_api(
    candidate_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("identity:read")),
):
    from app.services.identity_candidate_service import explainability_payload, get_identity_candidate_service

    row = get_identity_candidate_service().get_candidate(candidate_id)
    if row is None:
        return {"item": None, "status": "not_found", "detail": "Candidate not found"}
    if not can_access_identity_candidate(current_user, row):
        _audit(
            request,
            AuditAction.IDENTITY_CANDIDATE_ACCESS_DENIED,
            resource_type="identity_candidate",
            resource_id=candidate_id,
            success=False,
            detail="identity candidate access denied",
        )
        raise HTTPException(status_code=403, detail="Access denied")
    return _filter_identity_response(
        {"item": {**row, "explainability": explainability_payload(row)}, "status": "ok"},
        request,
    )


@router.post("/api/identity/candidates/{candidate_id}/accept")
def accept_identity_candidate_api(
    candidate_id: str,
    request: Request,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_api_permission("identity:write")),
):
    from app.services.identity_candidate_service import get_identity_candidate_service

    svc = get_identity_candidate_service()
    row = svc.get_candidate(candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    ensure_identity_candidate_access(request, current_user, row)
    notes = (payload or {}).get("review_notes")
    updated = svc.accept_candidate(candidate_id, reviewed_by=current_user.user_id, review_notes=notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _audit(
        request,
        AuditAction.IDENTITY_CANDIDATE_REVIEWED,
        resource_type="identity_candidate",
        resource_id=candidate_id,
        metadata={"review_status": "accepted", "operator_only": True},
    )
    return _filter_identity_response({"item": updated, "status": "ok"}, request)


@router.post("/api/identity/candidates/{candidate_id}/reject")
def reject_identity_candidate_api(
    candidate_id: str,
    request: Request,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_api_permission("identity:write")),
):
    from app.services.identity_candidate_service import get_identity_candidate_service

    svc = get_identity_candidate_service()
    row = svc.get_candidate(candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    ensure_identity_candidate_access(request, current_user, row)
    notes = (payload or {}).get("review_notes")
    updated = svc.reject_candidate(candidate_id, reviewed_by=current_user.user_id, review_notes=notes)
    if updated is None:
        raise HTTPException(status_code=400, detail="Reject not allowed")
    _audit(
        request,
        AuditAction.IDENTITY_CANDIDATE_REJECTED,
        resource_type="identity_candidate",
        resource_id=candidate_id,
        metadata={"review_status": "rejected"},
    )
    return _filter_identity_response({"item": updated, "status": "ok"}, request)


@router.post("/api/identity/candidates/{candidate_id}/escalate")
def escalate_identity_candidate_api(
    candidate_id: str,
    request: Request,
    payload: dict | None = Body(default=None),
    current_user: UserAccount = Depends(require_api_permission("identity:write")),
):
    from app.services.identity_candidate_service import get_identity_candidate_service

    svc = get_identity_candidate_service()
    row = svc.get_candidate(candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    ensure_identity_candidate_access(request, current_user, row)
    notes = (payload or {}).get("review_notes")
    updated = svc.escalate_candidate(candidate_id, reviewed_by=current_user.user_id, review_notes=notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    _audit(
        request,
        AuditAction.IDENTITY_CANDIDATE_ESCALATED,
        resource_type="identity_candidate",
        resource_id=candidate_id,
        metadata={"review_status": "escalated"},
    )
    return _filter_identity_response({"item": updated, "status": "ok"}, request)


@router.get("/api/identity/registry")
def list_global_identity_registry_api(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        items = [
            item
            for item in _identity_service().list_global_identities(status=status, limit=limit)
            if can_access_identity(_request_user(request), str(item.get("identity_id") or ""))
        ]
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.post("/api/identity/enroll")
async def enroll_identity_api(
    request: Request,
    files: list[UploadFile] = File(...),
    identity_id: Optional[str] = Form(default=None),
    display_name: Optional[str] = Form(default=None),
    metadata_json: Optional[str] = Form(default=None),
    current_user: UserAccount = Depends(require_api_permission("identity:write")),
):
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
        images = []
        accepted_uploads = []
        for file in files:
            content = await file.read()
            validation = get_upload_security_policy().validate(
                filename=file.filename or "upload.jpg",
                content=content,
                content_type=file.content_type,
                allowed_classes={"image"},
            )
            images.append({"filename": validation.normalized_filename, "data": content})
            accepted_uploads.append(validation)
        if identity_id:
            ensure_identity_access(request, current_user, identity_id)
        result = _identity_service().enroll(
            images,
            identity_id=identity_id,
            display_name=display_name,
            metadata=metadata,
        )
        _audit(
            request,
            AuditAction.FACE_ENROLLED,
            resource_type="identity_enrollment",
            resource_id=result.get("enrollment_id"),
            metadata={
                "identity_id": result.get("identity_id"),
                "accepted_images": result.get("accepted_images", 0),
                "rejected_images": result.get("rejected_images", 0),
                "sha256": [item.sha256 for item in accepted_uploads],
            },
        )
        return _filter_identity_response(result, request)
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/api/identity/enrollments")
def list_identity_enrollment_profiles_api(
    request: Request,
    identity_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: UserAccount = Depends(require_api_permission("identity:read")),
):
    try:
        if identity_id:
            ensure_identity_access(request, current_user, identity_id)
        items = [
            item
            for item in _identity_service().list_enrollment_profiles(identity_id=identity_id, limit=limit)
            if can_access_identity(current_user, str(item.get("identity_id") or ""))
        ]
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/identity/enrollments/{enrollment_id}")
def get_identity_enrollment_profile_api(
    enrollment_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("identity:read")),
):
    try:
        item = _identity_service().get_enrollment_profile(enrollment_id)
        if item is None:
            return {"item": None, "status": "not_found", "detail": f"Enrollment {enrollment_id} not found"}
        ensure_identity_access(request, current_user, str(item.get("identity_id") or ""))
        return _filter_identity_response({"item": item, "status": "ok"}, request)
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.get("/api/identity/enrollments/{enrollment_id}/images/{image_id}")
def get_identity_enrollment_image_api(
    enrollment_id: str,
    image_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("identity:read")),
):
    from fastapi.responses import FileResponse
    from app.services.face_enrollment_service import get_enrollment_service

    service = get_enrollment_service()
    policy = service.raw_asset_policy()
    audit_all = bool(policy.get("audit_all_access", True))
    if not service.is_raw_asset_http_enabled():
        if audit_all:
            _audit(
                request,
                AuditAction.ACCESS_DENIED,
                resource_type="identity_raw_asset",
                resource_id=image_id,
                success=False,
                detail="Raw identity enrollment asset retrieval disabled by policy",
                metadata={"enrollment_id": enrollment_id},
            )
        raise HTTPException(status_code=404, detail="Not found")
    try:
        asset = service.resolve_raw_enrollment_image(enrollment_id, image_id)
    except PermissionError:
        if audit_all:
            _audit(
                request,
                AuditAction.ACCESS_DENIED,
                resource_type="identity_raw_asset",
                resource_id=image_id,
                success=False,
                detail="Raw identity enrollment asset retrieval disabled by policy",
                metadata={"enrollment_id": enrollment_id},
            )
        raise HTTPException(status_code=404, detail="Not found")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Enrollment image '{image_id}' not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Enrollment image '{image_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    ensure_identity_access(request, current_user, str(asset.get("identity_id") or ""))
    if bool(policy.get("admin_only", True)) and str(current_user.role).lower() not in {"admin", "supervisor"}:
        if audit_all:
            _audit(
                request,
                AuditAction.ACCESS_DENIED,
                resource_type="identity_raw_asset",
                resource_id=image_id,
                success=False,
                detail="Admin approval required for raw identity asset retrieval",
                metadata={"enrollment_id": enrollment_id, "identity_id": asset.get("identity_id")},
            )
        raise HTTPException(status_code=403, detail="Insufficient permission")

    if audit_all:
        _audit(
            request,
            "identity_raw_asset_downloaded",
            resource_type="identity_raw_asset",
            resource_id=image_id,
            metadata={"enrollment_id": enrollment_id, "identity_id": asset.get("identity_id")},
        )
    return FileResponse(
        str(asset["path"]),
        media_type=str(asset.get("content_type") or "application/octet-stream"),
        filename=str(asset.get("filename") or Path(str(asset["path"])).name),
        headers=_sensitive_headers(),
    )


@router.delete("/api/identity/enrollments/{enrollment_id}")
def delete_identity_enrollment_profile_api(
    enrollment_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("identity:write")),
):
    try:
        profile = _identity_service().get_enrollment_profile(enrollment_id)
        if profile is not None:
            ensure_identity_access(request, current_user, str(profile.get("identity_id") or ""))
        ok = _identity_service().delete_enrollment_profile(enrollment_id)
        if not ok:
            return {"status": "not_found", "detail": f"Enrollment {enrollment_id} not found"}
        _audit(
            request,
            AuditAction.IDENTITY_UPDATED,
            resource_type="identity_enrollment",
            resource_id=enrollment_id,
            detail="Enrollment profile deleted",
        )
        return {"status": "ok", "detail": "Enrollment deleted"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/api/identities")
def list_identities_api(
    request: Request,
    status: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    try:
        store = _id_store()
        items = [
            p.to_dict()
            for p in store.list_identities(status=status, tag=tag, limit=limit)
            if can_access_identity(_request_user(request), p.identity_id)
        ]
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.post("/api/identities")
async def create_identity_api(payload: dict, request: Request):
    try:
        store = _id_store()
        profile = store.create_identity(
            display_name=payload.get("display_name"),
            tags=payload.get("tags", []),
            notes=payload.get("notes"),
            metadata=payload.get("metadata", {}),
        )
        try:
            get_metrics().increment("identities_registered")
        except Exception:
            pass
        _audit(request, AuditAction.IDENTITY_CREATED, resource_type="identity", resource_id=profile.identity_id)
        return _filter_identity_response({"item": profile.to_dict(), "status": "ok"}, request)
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.get("/api/identities/{identity_id}")
def get_identity_api(identity_id: str, request: Request):
    _require_object_access(request, "identity", identity_id, can_access_identity(_request_user(request), identity_id))
    try:
        store = _id_store()
        profile = store.get_identity(identity_id)
        if not profile:
            return {
                "item": None,
                "status": "not_found",
                "detail": f"Identity {identity_id} not found",
            }
        _audit(request, AuditAction.IDENTITY_VIEWED, resource_type="identity", resource_id=identity_id)
        return _filter_identity_response({"item": profile.to_dict(), "status": "ok"}, request)
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.patch("/api/identities/{identity_id}")
async def update_identity_api(identity_id: str, payload: dict, request: Request):
    ensure_identity_access(request, _request_user(request), identity_id)
    try:
        store = _id_store()
        profile = store.update_identity(identity_id, payload)
        if not profile:
            return {
                "item": None,
                "status": "not_found",
                "detail": f"Identity {identity_id} not found",
            }
        _audit(request, AuditAction.IDENTITY_UPDATED, resource_type="identity", resource_id=identity_id, metadata={"updated_fields": sorted(payload.keys())})
        return _filter_identity_response({"item": profile.to_dict(), "status": "ok"}, request)
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.delete("/api/identities/{identity_id}")
def archive_identity_api(identity_id: str, request: Request):
    ensure_identity_access(request, _request_user(request), identity_id)
    try:
        store = _id_store()
        ok = store.archive_identity(identity_id)
        if not ok:
            return {"status": "not_found", "detail": f"Identity {identity_id} not found"}
        _audit(request, AuditAction.IDENTITY_UPDATED, resource_type="identity", resource_id=identity_id, detail="Identity archived")
        return {"status": "ok", "detail": "Identity archived"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.post("/api/identities/{identity_id}/enroll-face")
async def enroll_face_api(
    identity_id: str,
    request: Request,
    file: UploadFile = File(...),
    display_name: Optional[str] = Query(default=None),
):
    try:
        ensure_identity_access(request, _request_user(request), identity_id)
        data = await file.read()
        validation = get_upload_security_policy().validate(
            filename=file.filename or "enrollment.jpg",
            content=data,
            content_type=file.content_type,
            allowed_classes={"image"},
        )
        result = _identity_service().enroll(
            [{"filename": validation.normalized_filename, "data": data}],
            identity_id=identity_id,
            display_name=display_name,
        )
        _audit(
            request,
            AuditAction.FACE_ENROLLED,
            resource_type="identity",
            resource_id=identity_id,
            metadata={"enrollment_id": result.get("enrollment_id"), "sha256": validation.sha256},
        )
        return _filter_identity_response(result, request)
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/api/identities/{identity_id}/enrollments")
def list_identity_enrollments_api(identity_id: str, request: Request):
    try:
        ensure_identity_access(request, _request_user(request), identity_id)
        items = _identity_service().list_face_enrollments(identity_id)
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/identities/{identity_id}/matches")
def list_identity_matches_api(
    identity_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        ensure_identity_access(request, _request_user(request), identity_id)
        store = _id_store()
        matches = store.list_matches(identity_id=identity_id, limit=limit)
        items = [m.to_dict() for m in matches]
        return _filter_identity_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


# ============================================================
# WATCHLIST ENDPOINTS (Phase 20)
# ============================================================

@router.get("/api/watchlist")
def list_watchlist_api(
    request: Request,
    active: bool = Query(default=True),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        store = _wl_store()
        entries = [
            entry
            for entry in store.list_watchlist(active=active, severity=severity, limit=limit)
            if can_access_watchlist(_request_user(request), entry.watchlist_id)
            or can_access_identity(_request_user(request), entry.identity_id)
        ]
        items = [e.to_dict() for e in entries]
        try:
            metrics.increment("watchlist_sensitive_reads")
        except Exception:
            pass
        return _filter_watchlist_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.post("/api/watchlist")
async def add_watchlist_entry_api(payload: dict, request: Request):
    try:
        import time as _time
        ensure_identity_access(request, _request_user(request), str(payload.get("identity_id") or ""))
        store = _wl_store()
        expires_at = None
        if payload.get("expires_days"):
            expires_at = _time.time() + float(payload["expires_days"]) * 86400
        entry = store.add_to_watchlist(
            identity_id=payload["identity_id"],
            severity=payload.get("severity", "medium"),
            reason=payload.get("reason"),
            expires_at=expires_at,
            metadata=payload.get("metadata", {}),
        )
        # Reflect watchlisted status on the identity record
        _id_store().update_identity(entry.identity_id, {"status": "watchlisted"})
        try:
            get_metrics().increment("watchlist_entries_active")
        except Exception:
            pass
        _audit(request, AuditAction.WATCHLIST_UPDATED, resource_type="watchlist", resource_id=entry.watchlist_id, detail="Watchlist entry added")
        return _filter_watchlist_response({"item": entry.to_dict(), "status": "ok"}, request)
    except KeyError as exc:
        return {"item": None, "status": "error", "detail": f"Missing required field: {exc}"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.delete("/api/watchlist/{watchlist_id}")
def remove_watchlist_entry_api(watchlist_id: str, request: Request):
    try:
        ensure_watchlist_access(request, _request_user(request), watchlist_id)
        store = _wl_store()
        ok = store.remove_from_watchlist(watchlist_id)
        if not ok:
            return {
                "status": "not_found",
                "detail": f"Watchlist entry {watchlist_id} not found",
            }
        _audit(request, AuditAction.WATCHLIST_UPDATED, resource_type="watchlist", resource_id=watchlist_id, detail="Watchlist entry removed")
        return {"status": "ok", "detail": "Entry removed"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/api/watchlist/identity/{identity_id}")
def get_identity_watchlist_api(identity_id: str, request: Request):
    try:
        ensure_identity_access(request, _request_user(request), identity_id)
        store = _wl_store()
        entries = store.get_identity_watchlist(identity_id)
        items = [e.to_dict() for e in entries]
        try:
            metrics.increment("watchlist_sensitive_reads")
        except Exception:
            pass
        return _filter_watchlist_response({"items": items, "count": len(items), "status": "ok" if items else "empty"}, request)
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


# ============================================================
# OPEN-VOCABULARY THREAT SCANNER ENDPOINTS (Phase 23)
# ============================================================

class OpenVocabPromptCreateRequest(BaseModel):
    text: str
    category: str
    severity: str = "medium"
    threshold: Optional[float] = None
    metadata: Optional[dict] = None


class OpenVocabPromptUpdateRequest(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    threshold: Optional[float] = None
    enabled: Optional[bool] = None
    metadata: Optional[dict] = None


class OpenVocabScanRequest(BaseModel):
    prompts: Optional[list] = None


def _get_open_vocab_scanner():
    """Return the open-vocab scanner from the intelligence runtime (or None)."""
    try:
        return _get_intelligence_runtime().open_vocab_scanner
    except Exception:
        return None


@router.get("/api/open-vocab/status")
def open_vocab_status_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """Return open-vocabulary scanner status and metrics."""
    try:
        runtime = _get_intelligence_runtime()
        status = runtime.get_open_vocab_status()
        _audit(request, AuditAction.OPEN_VOCAB_SCAN, resource_type="open_vocab", detail="Status read")
        return {"item": status, "status": "ok"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.get("/api/open-vocab/prompts")
def list_open_vocab_prompts_api(
    request: Request,
    category: Optional[str] = Query(default=None),
    enabled: Optional[bool] = Query(default=None),
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """List open-vocabulary prompts, optionally filtered by category or enabled."""
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"items": [], "count": 0, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}
        library = scanner.get_prompt_library()
        items = library.list_prompts(category=category, enabled=enabled)
        return {"items": items, "count": len(items), "status": "ok" if items else "empty"}
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.post("/api/open-vocab/prompts")
def create_open_vocab_prompt_api(
    body: OpenVocabPromptCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Create a new open-vocabulary prompt."""
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"item": None, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}
        library = scanner.get_prompt_library()
        prompt = library.add_prompt(
            text=body.text,
            category=body.category,
            severity=body.severity,
            threshold=body.threshold,
            metadata=body.metadata or {},
        )
        _audit(request, AuditAction.OPEN_VOCAB_PROMPT_CREATED, resource_type="open_vocab_prompt",
               resource_id=prompt["prompt_id"], metadata={"text": body.text, "category": body.category})
        return {"item": prompt, "status": "ok"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.patch("/api/open-vocab/prompts/{prompt_id}")
def update_open_vocab_prompt_api(
    prompt_id: str,
    body: OpenVocabPromptUpdateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Update an existing open-vocabulary prompt."""
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"item": None, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}
        library = scanner.get_prompt_library()
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        prompt = library.update_prompt(prompt_id, updates)
        if prompt is None:
            return {"item": None, "status": "not_found", "detail": f"Prompt '{prompt_id}' not found"}
        _audit(request, AuditAction.OPEN_VOCAB_PROMPT_UPDATED, resource_type="open_vocab_prompt",
               resource_id=prompt_id, metadata={"updated_fields": sorted(updates.keys())})
        return {"item": prompt, "status": "ok"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.post("/api/open-vocab/prompts/{prompt_id}/disable")
def disable_open_vocab_prompt_api(
    prompt_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Disable an open-vocabulary prompt."""
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"item": None, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}
        library = scanner.get_prompt_library()
        ok = library.disable_prompt(prompt_id)
        if not ok:
            return {"item": None, "status": "not_found", "detail": f"Prompt '{prompt_id}' not found"}
        _audit(request, AuditAction.OPEN_VOCAB_PROMPT_UPDATED, resource_type="open_vocab_prompt",
               resource_id=prompt_id, detail="Prompt disabled")
        return {"item": library.get_prompt(prompt_id), "status": "ok"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.post("/api/open-vocab/scan/latest-frame/{camera_id}")
def open_vocab_scan_latest_frame_api(
    camera_id: str,
    request: Request,
    body: Optional[OpenVocabScanRequest] = None,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Trigger an open-vocabulary scan on the latest frame from a camera."""
    ensure_camera_access(request, current_user, camera_id)
    prompts = (body.prompts if body and body.prompts else None)
    try:
        runtime = _get_intelligence_runtime()
        result = runtime.scan_open_vocab_latest(camera_id, prompts=prompts)
        _audit(request, AuditAction.OPEN_VOCAB_SCAN, resource_type="camera",
               resource_id=camera_id, metadata={"source": "latest_frame"})
        scan_status = result.get("status", "ok")
        if scan_status in ("unavailable", "error"):
            return {"item": result, "status": scan_status, "detail": result.get("error") or result.get("reason")}
        return {"item": result, "status": "ok"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.post("/api/open-vocab/scan/incident/{incident_id}")
def open_vocab_scan_incident_api(
    incident_id: str,
    request: Request,
    body: Optional[OpenVocabScanRequest] = None,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Trigger an open-vocabulary scan on incident frame references."""
    ensure_incident_access(request, current_user, incident_id)
    prompts = (body.prompts if body and body.prompts else None)
    try:
        runtime = _get_intelligence_runtime()
        result = runtime.scan_open_vocab_incident(incident_id, prompts=prompts)
        _audit(request, AuditAction.OPEN_VOCAB_SCAN, resource_type="incident",
               resource_id=incident_id, metadata={"source": "incident"})
        scan_status = result.get("status", "ok")
        if scan_status in ("unavailable", "error"):
            return {"item": result, "status": scan_status, "detail": result.get("error") or result.get("reason")}
        return {"item": result, "status": "ok"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.post("/api/open-vocab/scan/image")
async def open_vocab_scan_image_api(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(require_api_permission("open_vocab:write")),
):
    """Scan an uploaded image using open-vocabulary prompts."""
    import json as _json
    content = await file.read()
    validation = get_upload_security_policy().validate(
        filename=file.filename or "upload.jpg",
        content=content,
        content_type=file.content_type,
        allowed_classes={"image"},
    )

    # Extract prompts from form (may be JSON array or missing)
    form = await request.form()
    prompts = None
    raw_prompts = form.get("prompts")
    if raw_prompts:
        try:
            prompts = _json.loads(raw_prompts)
            if not isinstance(prompts, list):
                prompts = None
        except Exception:
            prompts = None

    # Save temp file safely
    upload_dir = "storage/open_vocab/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    import uuid as _uuid
    safe_name = f"{_uuid.uuid4().hex}{validation.extension}"
    temp_path = os.path.join(upload_dir, safe_name)
    try:
        with open(temp_path, "wb") as fout:
            fout.write(content)

        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"item": None, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}

        result = scanner.scan_image(
            image_path=temp_path,
            prompts=prompts,
            source="upload",
        )
        _audit(request, AuditAction.OPEN_VOCAB_SCAN, resource_type="open_vocab",
               detail="Image scan via upload", metadata={"filename": validation.normalized_filename, "sha256": validation.sha256})
        # Do not expose temp path in response
        result.pop("image_path", None)
        result.pop("upload_path", None)
        result.pop("temp_path", None)
        return {"item": result, "status": result.get("status", "ok")}
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


@router.get("/api/open-vocab/results")
def list_open_vocab_results_api(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """List recent open-vocabulary scan results."""
    try:
        runtime = _get_intelligence_runtime()
        response = runtime.get_open_vocab_results(limit=limit)
        response["items"] = [
            item
            for item in response.get("items", [])
            if can_access_event_payload(current_user, item)
            or can_access_camera(current_user, str(item.get("camera_id") or ""))
            or can_access_incident(current_user, str(item.get("incident_id") or ""))
        ]
        response["count"] = len(response["items"])
        return response
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/open-vocab/results/{scan_id}")
def get_open_vocab_result_api(
    scan_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """Get a specific open-vocabulary scan result by scan_id."""
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"item": None, "status": "unavailable", "detail": "Open-vocab scanner not initialized"}
        result = scanner.get_result_store().get_result(scan_id)
        if result is None:
            return {"item": None, "status": "not_found", "detail": f"Scan '{scan_id}' not found"}
        if result.get("camera_id"):
            ensure_camera_access(request, current_user, str(result.get("camera_id")))
        elif result.get("incident_id"):
            ensure_incident_access(request, current_user, str(result.get("incident_id")))
        else:
            ensure_event_payload_access(request, current_user, resource_id=scan_id, payload=result)
        return {"item": result, "status": "ok"}
    except Exception as exc:
        return {"item": None, "status": "error", "detail": str(exc)}


@router.get("/api/open-vocab/results/camera/{camera_id}")
def get_open_vocab_results_by_camera_api(
    camera_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """List open-vocabulary scan results for a specific camera."""
    ensure_camera_access(request, current_user, camera_id)
    try:
        runtime = _get_intelligence_runtime()
        response = runtime.get_open_vocab_results(camera_id=camera_id, limit=limit)
        return response
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


@router.get("/api/open-vocab/results/incident/{incident_id}")
def get_open_vocab_results_by_incident_api(
    incident_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """List open-vocabulary scan results for a specific incident."""
    ensure_incident_access(request, current_user, incident_id)
    try:
        runtime = _get_intelligence_runtime()
        response = runtime.get_open_vocab_results(incident_id=incident_id, limit=limit)
        return response
    except Exception as exc:
        return {"items": [], "count": 0, "status": "error", "detail": str(exc)}


# ============================================================
# OPEN-VOCAB MODEL HOT-LOAD ENDPOINTS (Phase 24)
# ============================================================

def _ov_load_metrics(event: str) -> None:
    """Increment an open-vocab model lifecycle metric counter safely."""
    try:
        from inference.monitoring.metrics import get_metrics as get_mon
        get_mon().increment(event)
    except Exception:
        pass
    try:
        metrics.increment(event)
    except Exception:
        pass


@router.post("/api/open-vocab/model/load")
def open_vocab_model_load_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:model")),
):
    """
    Hot-load the open-vocabulary model adapter.

    Reads AEGIS_OPEN_VOCAB_MODEL_PATH and AEGIS_OPEN_VOCAB_PROCESSOR_PATH from
    environment, applies them to the adapter config, and calls adapter.load().
    Returns a structured error (not 500) when paths are missing and download
    is disabled.
    """
    import os as _os
    _ov_load_metrics("open_vocab_model_load_attempts")

    model_path = _os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
    processor_path = _os.environ.get("AEGIS_OPEN_VOCAB_PROCESSOR_PATH", "")
    allow_download = _os.environ.get("AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD", "false").lower() == "true"

    if not model_path and not allow_download:
        _ov_load_metrics("open_vocab_model_load_failures")
        return {
            "status": "unavailable",
            "detail": "AEGIS_OPEN_VOCAB_MODEL_PATH not set and AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD is false",
            "loaded": False,
        }

    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            _ov_load_metrics("open_vocab_model_load_failures")
            return {"status": "unavailable", "detail": "Open-vocab scanner not initialized", "loaded": False}

        adapter = getattr(scanner, "adapter", None) or getattr(scanner, "_adapter", None)
        if adapter is None:
            _ov_load_metrics("open_vocab_model_load_failures")
            return {"status": "error", "detail": "Adapter not accessible on scanner", "loaded": False}

        # Push env-sourced paths into the adapter before loading
        config_override: dict = {}
        if model_path:
            config_override["local_model_path"] = model_path
        if processor_path:
            config_override["local_processor_path"] = processor_path
        if allow_download:
            adapter._config["allow_huggingface_download"] = True

        if hasattr(adapter, "set_config_override") and config_override:
            adapter.set_config_override(config_override)

        adapter.load()
        adapter_status = adapter.get_status() if hasattr(adapter, "get_status") else {}

        if adapter_status.get("available"):
            _ov_load_metrics("open_vocab_model_load_success")
            _audit(request, AuditAction.MODEL_UPDATED, resource_type="open_vocab_model",
                   detail="Model loaded successfully")
            return {"status": "ok", "loaded": True, "adapter": adapter_status}
        else:
            _ov_load_metrics("open_vocab_model_load_failures")
            reason = adapter_status.get("reason", "Load did not succeed")
            return {"status": "error", "loaded": False, "detail": reason, "adapter": adapter_status}
    except Exception as exc:
        _ov_load_metrics("open_vocab_model_load_failures")
        logger.error("open_vocab model load error: %s", exc)
        return {"status": "error", "loaded": False, "detail": str(exc)[:200]}


@router.post("/api/open-vocab/model/unload")
def open_vocab_model_unload_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:model")),
):
    """Unload the open-vocabulary model adapter to free memory."""
    _ov_load_metrics("open_vocab_model_unloads")
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"status": "unavailable", "detail": "Open-vocab scanner not initialized", "loaded": False}

        adapter = getattr(scanner, "adapter", None) or getattr(scanner, "_adapter", None)
        if adapter is None:
            return {"status": "error", "detail": "Adapter not accessible on scanner", "loaded": False}

        if hasattr(adapter, "unload"):
            adapter.unload()

        _audit(request, AuditAction.MODEL_UPDATED, resource_type="open_vocab_model", detail="Model unloaded")
        adapter_status = adapter.get_status() if hasattr(adapter, "get_status") else {}
        return {"status": "ok", "loaded": False, "adapter": adapter_status}
    except Exception as exc:
        logger.error("open_vocab model unload error: %s", exc)
        return {"status": "error", "detail": str(exc)[:200]}


@router.post("/api/open-vocab/model/reload")
def open_vocab_model_reload_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:model")),
):
    """Unload then re-load the open-vocabulary model adapter (hot-reload)."""
    _ov_load_metrics("open_vocab_model_load_attempts")
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            _ov_load_metrics("open_vocab_model_load_failures")
            return {"status": "unavailable", "detail": "Open-vocab scanner not initialized", "loaded": False}

        adapter = getattr(scanner, "adapter", None) or getattr(scanner, "_adapter", None)
        if adapter is None:
            _ov_load_metrics("open_vocab_model_load_failures")
            return {"status": "error", "detail": "Adapter not accessible on scanner", "loaded": False}

        # Unload first
        if hasattr(adapter, "unload"):
            adapter.unload()

        # Re-apply env paths
        import os as _os
        model_path = _os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
        processor_path = _os.environ.get("AEGIS_OPEN_VOCAB_PROCESSOR_PATH", "")
        config_override: dict = {}
        if model_path:
            config_override["local_model_path"] = model_path
        if processor_path:
            config_override["local_processor_path"] = processor_path
        if hasattr(adapter, "set_config_override") and config_override:
            adapter.set_config_override(config_override)

        adapter.load()
        adapter_status = adapter.get_status() if hasattr(adapter, "get_status") else {}

        if adapter_status.get("available"):
            _ov_load_metrics("open_vocab_model_load_success")
            _audit(request, AuditAction.MODEL_UPDATED, resource_type="open_vocab_model", detail="Model reloaded")
            return {"status": "ok", "loaded": True, "adapter": adapter_status}
        else:
            _ov_load_metrics("open_vocab_model_load_failures")
            reason = adapter_status.get("reason", "Reload did not succeed")
            return {"status": "error", "loaded": False, "detail": reason, "adapter": adapter_status}
    except Exception as exc:
        _ov_load_metrics("open_vocab_model_load_failures")
        logger.error("open_vocab model reload error: %s", exc)
        return {"status": "error", "loaded": False, "detail": str(exc)[:200]}


@router.get("/api/open-vocab/model/status")
def open_vocab_model_status_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("open_vocab:read")),
):
    """
    Return the current load status of the open-vocabulary model adapter.

    Reports provider, loaded state, device, and whether model/processor paths
    are configured (boolean only — no raw paths exposed to non-admin callers).
    """
    import os as _os
    try:
        scanner = _get_open_vocab_scanner()
        if scanner is None:
            return {"status": "unavailable", "detail": "Open-vocab scanner not initialized", "adapter": None}

        adapter = getattr(scanner, "adapter", None) or getattr(scanner, "_adapter", None)
        if adapter is None:
            return {"status": "ok", "adapter": None, "detail": "No adapter attached"}

        raw_status = scanner.get_status() if hasattr(scanner, "get_status") else {}
        model_path = _os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
        processor_path = _os.environ.get("AEGIS_OPEN_VOCAB_PROCESSOR_PATH", "")

        # Redact paths for non-admin users; expose boolean only
        is_admin = getattr(current_user, "role", "") in {"admin", "supervisor"}
        public_status = {
            "provider": raw_status.get("adapter", {}).get("provider"),
            "available": raw_status.get("model_loaded", False),
            "loaded": raw_status.get("model_loaded", False),
            "device": raw_status.get("adapter", {}).get("device"),
            "model_path_configured": bool(model_path),
            "processor_path_configured": bool(processor_path),
            "last_load_error": raw_status.get("adapter", {}).get("reason") if not raw_status.get("model_loaded") else None,
            "auto_load_on_camera_start": raw_status.get("auto_load_on_camera_start", False),
            "last_auto_load_status": raw_status.get("last_auto_load_status"),
            "last_auto_load_error": raw_status.get("last_auto_load_error"),
        }
        if is_admin:
            public_status["model_id"] = raw_status.get("adapter", {}).get("model_id")

        return {"status": "ok", "adapter": public_status}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:200], "adapter": None}
