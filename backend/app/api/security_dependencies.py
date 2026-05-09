from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.security.config import auth_required, get_rbac_config
from app.security.permissions import has_permission
from app.services.audit_log_service import get_audit_log_service
from app.services.auth_service import get_auth_service


PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/auth/login",
}


def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        cookie_token = request.cookies.get("aegis_access_token")
        return cookie_token or None
    token = header.split(" ", 1)[1].strip()
    return token or None


def _structured_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "error", "detail": detail})


def get_current_user_from_request(request: Request) -> UserAccount | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, UserAccount) else None


def _local_dev_user() -> UserAccount:
    now = time.time()
    return UserAccount(
        user_id="local-dev",
        username="local-dev",
        display_name="Local Development",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="",
        created_at=now,
        updated_at=now,
        metadata={"auth_required": False},
    )


async def optional_user(request: Request) -> UserAccount | None:
    existing = get_current_user_from_request(request)
    if existing is not None:
        return existing
    token = _extract_bearer_token(request)
    if not token:
        return None
    user = get_auth_service().get_current_user_from_token(token)
    if user is not None:
        request.state.current_user = user
    return user


async def get_current_user(request: Request) -> UserAccount:
    if not auth_required():
        user = get_current_user_from_request(request)
        if user is not None:
            return user
        user = _local_dev_user()
        request.state.current_user = user
        return user

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = get_auth_service().get_current_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(status_code=403, detail="User account is not active")
    request.state.current_user = user
    return user


async def require_auth(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
    return current_user


def require_permission(permission: str) -> Callable:
    async def dependency(
        request: Request,
        current_user: UserAccount = Depends(get_current_user),
    ) -> UserAccount:
        if not auth_required():
            return current_user
        if not has_permission(current_user.role, permission, get_rbac_config()):
            record_access_denied(
                request,
                current_user,
                detail=f"Permission required: {permission}",
                metadata={"permission": permission},
            )
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return current_user

    return dependency


def record_access_denied(
    request: Request,
    user: UserAccount | None,
    detail: str,
    metadata: dict | None = None,
) -> None:
    try:
        from inference.metrics import metrics
        metrics.increment("auth_access_denied")
    except Exception:
        pass
    try:
        get_audit_log_service().record(
            AuditAction.ACCESS_DENIED,
            user=user,
            resource_type="api",
            resource_id=request.url.path,
            success=False,
            detail=detail,
            request=request,
            metadata={"method": request.method, **(metadata or {})},
        )
    except Exception:
        pass


def permission_for_request(method: str, path: str) -> str | None:
    method = method.upper()
    if path.startswith("/api/auth/"):
        return None
    if path.startswith("/api/security/users"):
        return "admin"
    if path.startswith("/api/audit/"):
        return "audit:read"
    if path == "/api/security/roles":
        return None

    if path in {"/metrics", "/api/metrics", "/metrics/core", "/api/metrics/core"}:
        return "metrics:read"
    if path.startswith("/config/"):
        return "metrics:read"
    if path in {"/events", "/detections"}:
        return "alert:read"
    if path == "/process-video":
        return "camera:control"

    if path in {"/streams", "/api/streams"} or path.startswith("/api/streams/"):
        return "camera:read" if method == "GET" else "camera:control"
    if path in {"/streams/add", "/streams/remove"}:
        return "camera:control"

    if path.startswith("/api/alerts"):
        return "alert:read" if method == "GET" else "alert:write"
    if path.startswith("/api/incidents"):
        if path.endswith("/replay"):
            return "forensics:read"
        return "incident:read" if method == "GET" else "incident:write"
    if path.startswith("/incidents"):
        return "incident:read"
    if path.startswith("/api/timeline/") or path.startswith("/timeline/"):
        return "forensics:read"
    if path.startswith("/api/anomalies/") or path.startswith("/anomalies/"):
        return "alert:read"

    if path.startswith("/api/cameras"):
        if method == "GET":
            return "camera:read"
        return "camera:control"
    if path.startswith("/cameras/"):
        return "camera:read"

    if path.startswith("/api/map/"):
        return "map:read"
    if path.startswith("/api/handoffs/"):
        return "map:read"

    if path.startswith("/api/models"):
        return "model:read" if method == "GET" else "model:write"

    if path.startswith("/api/identities"):
        if method == "GET":
            return "identity:read"
        return "identity:write"
    if path.startswith("/api/watchlist"):
        if method == "GET":
            return "watchlist:read"
        return "watchlist:write"

    if path.startswith("/api/"):
        return None
    return None


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/assets/"):
        return True
    return False


async def enforce_request_security(request: Request, call_next):
    if not auth_required():
        return await call_next(request)

    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    required_permission = permission_for_request(request.method, path)
    requires_auth = required_permission is not None or path.startswith("/api/")
    if not requires_auth:
        return await call_next(request)

    token = _extract_bearer_token(request)
    if not token:
        record_access_denied(request, None, "Authentication required")
        return _structured_error(401, "Authentication required")

    user = get_auth_service().get_current_user_from_token(token)
    if user is None:
        record_access_denied(request, None, "Invalid or expired token")
        return _structured_error(401, "Invalid or expired token")
    if user.status != UserStatus.ACTIVE.value:
        record_access_denied(request, user, "User account is not active")
        return _structured_error(403, "User account is not active")

    request.state.current_user = user
    if required_permission and not has_permission(user.role, required_permission, get_rbac_config()):
        record_access_denied(
            request,
            user,
            detail=f"Permission required: {required_permission}",
            metadata={"permission": required_permission},
        )
        return _structured_error(403, "Insufficient permission")

    return await call_next(request)
