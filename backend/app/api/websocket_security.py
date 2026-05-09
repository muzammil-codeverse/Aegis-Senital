from __future__ import annotations

import time
from collections.abc import Iterable

from fastapi import WebSocket

from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.security.config import auth_required, get_auth_config, get_rbac_config
from app.security.permissions import has_permission
from app.services.audit_log_service import get_audit_log_service
from app.services.auth_service import get_auth_service


def extract_ws_token(websocket) -> str | None:
    auth_cfg = get_auth_config()
    if bool(auth_cfg.get("allow_query_token_for_websocket", True)):
        token = websocket.query_params.get("token")
        if token:
            return token
    cookie_name = str(auth_cfg.get("cookie_name") or "aegis_access_token")
    cookie_token = websocket.cookies.get(cookie_name)
    if cookie_token:
        return cookie_token
    protocol = websocket.headers.get("sec-websocket-protocol") or ""
    for part in protocol.split(","):
        value = part.strip()
        if value.lower().startswith("bearer."):
            return value.split(".", 1)[1].strip() or None
        if value.lower().startswith("token."):
            return value.split(".", 1)[1].strip() or None
    return None


async def reject_ws(
    websocket,
    code: int = 1008,
    reason: str = "Authentication required",
):
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        pass


async def authenticate_websocket(
    websocket: WebSocket,
    required_permission: str | Iterable[str] | None = None,
):
    permissions = _normalize_permissions(required_permission)
    if not auth_required():
        user = _local_dev_user()
        websocket.state.current_user = user
        return user

    token = extract_ws_token(websocket)
    if not token:
        await _deny(websocket, None, "Authentication required", permissions)
        return None

    user = get_auth_service().get_current_user_from_token(token)
    if user is None:
        await _deny(websocket, None, "Invalid or expired token", permissions)
        return None
    if user.status != UserStatus.ACTIVE.value:
        await _deny(websocket, user, "User account is not active", permissions)
        return None
    if permissions and not any(has_permission(user.role, permission, get_rbac_config()) for permission in permissions):
        await _deny(websocket, user, "Insufficient permission", permissions)
        return None

    websocket.state.current_user = user
    _metric("websocket_auth_success")
    get_audit_log_service().record(
        AuditAction.WEBSOCKET_CONNECTED,
        user=user,
        resource_type="websocket",
        resource_id=websocket.url.path,
        request=websocket,
        metadata={"permissions": permissions},
    )
    return user


def _normalize_permissions(required_permission: str | Iterable[str] | None) -> list[str]:
    if required_permission is None:
        return []
    if isinstance(required_permission, str):
        return [required_permission]
    return [str(item) for item in required_permission]


async def _deny(websocket: WebSocket, user: UserAccount | None, detail: str, permissions: list[str]) -> None:
    _metric("websocket_auth_failed")
    get_audit_log_service().record(
        AuditAction.WEBSOCKET_DENIED,
        user=user,
        resource_type="websocket",
        resource_id=websocket.url.path,
        success=False,
        detail=detail,
        request=websocket,
        metadata={"permissions": permissions},
    )
    await reject_ws(websocket, code=1008, reason=detail)


def _metric(name: str) -> None:
    try:
        from inference.metrics import metrics
        metrics.increment(name)
    except Exception:
        pass


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
