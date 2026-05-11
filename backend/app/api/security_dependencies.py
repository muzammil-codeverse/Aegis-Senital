from __future__ import annotations

import secrets
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.security.config import auth_required, get_auth_config, get_rbac_config
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
CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
}
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _authorization_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    return token or None


def _cookie_token(request: Request) -> str | None:
    cookie_name = str(get_auth_config().get("cookie_name") or "aegis_access_token")
    cookie_token = request.cookies.get(cookie_name)
    return cookie_token or None


def _extract_bearer_token(request: Request) -> str | None:
    token = _authorization_token(request)
    if token:
        return token
    return _cookie_token(request)


def _using_cookie_auth(request: Request) -> bool:
    return _authorization_token(request) is None and _cookie_token(request) is not None


def _validate_csrf(request: Request) -> None:
    auth_cfg = get_auth_config()
    if request.method.upper() in CSRF_SAFE_METHODS:
        return
    if request.url.path in CSRF_EXEMPT_PATHS:
        return
    if not bool(auth_cfg.get("csrf_protect_cookie_auth", True)):
        return
    if not _using_cookie_auth(request):
        return
    header_name = str(auth_cfg.get("csrf_header_name") or "X-CSRF-Token")
    cookie_name = str(auth_cfg.get("csrf_cookie_name") or "aegis_csrf_token")
    header_token = (request.headers.get(header_name) or "").strip()
    cookie_token = (request.cookies.get(cookie_name) or "").strip()
    if header_token and cookie_token and secrets.compare_digest(header_token, cookie_token):
        return
    raise HTTPException(status_code=403, detail="CSRF validation failed")


def _structured_error(status_code: int, detail: str, permission: str | None = None) -> JSONResponse:
    content = {"status": "error", "detail": detail}
    if permission:
        content["permission"] = permission
    return JSONResponse(status_code=status_code, content=content)


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
    _validate_csrf(request)
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
    if path.startswith("/api/system/"):
        return "system:read"
    if path == "/api/analytics/export":
        return "analytics:export"
    if path.startswith("/api/analytics"):
        return "analytics:read"
    if path.startswith("/api/llm/"):
        if method == "GET":
            return "llm:read"
        if path.endswith("/report"):
            return "llm:report"
        return "llm:write"
    if path == "/api/security/roles":
        return None

    if path in {"/metrics", "/api/metrics", "/metrics/core", "/api/metrics/core"}:
        return "metrics:read"
    if path.startswith("/config/"):
        return "metrics:read"
    if path in {"/events", "/detections"}:
        return "event:read"
    if path == "/process-video":
        return "camera:control"

    if path in {"/streams", "/api/streams"}:
        return "stream:read" if method == "GET" else "stream:write"
    if path.startswith("/api/streams/"):
        if "/replay/" in path:
            return "stream:replay"
        if path.endswith("/start") or path.endswith("/stop") or path.endswith("/restart"):
            return "stream:write"
        if "/webrtc/" in path and method != "GET":
            return "stream:write" if path.endswith("/stop") else "stream:read"
        return "stream:read" if method == "GET" else "stream:write"
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

    if path.startswith("/api/open-vocab/model/"):
        return "open_vocab:read" if method == "GET" else "open_vocab:model"
    if path.startswith("/api/open-vocab/"):
        if method == "GET":
            return "open_vocab:read"
        return "open_vocab:write"

    if path.startswith("/api/identities"):
        if method == "GET":
            return "identity:read"
        return "identity:write"
    if path.startswith("/api/identity"):
        if method == "GET":
            return "identity:read"
        return "identity:write"
    if path.startswith("/api/watchlist"):
        if method == "GET":
            return "watchlist:read"
        return "watchlist:write"
    if path.startswith("/api/handoffs/"):
        return "incident:read"
    if path == "/api/cases" or path.startswith("/api/cases/"):
        if "/enrichment" in path:
            if method == "GET":
                return "osint:read"
            if path.endswith("/summarize"):
                return "osint:summarize"
            return "osint:write"
        if method == "GET":
            if path.endswith("/export"):
                return "case:export"
            return "case:read"
        if path.endswith("/assign"):
            return "case:assign"
        if any(path.endswith(suffix) for suffix in ("/close", "/reopen", "/dismiss", "/archive")):
            return "case:close"
        return "case:write"

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

    # Let the CORS middleware answer browser preflight requests without auth.
    if request.method.upper() == "OPTIONS":
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
    try:
        _validate_csrf(request)
    except HTTPException as exc:
        record_access_denied(request, user, str(exc.detail), metadata={"csrf": True})
        return _structured_error(exc.status_code, str(exc.detail))
    if required_permission and not has_permission(user.role, required_permission, get_rbac_config()):
        record_access_denied(
            request,
            user,
            detail=f"Permission required: {required_permission}",
            metadata={"permission": required_permission},
        )
        return _structured_error(403, "Insufficient permission", required_permission)

    return await call_next(request)
