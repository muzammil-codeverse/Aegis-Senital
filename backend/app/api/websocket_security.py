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
    token, _source, _detail = _extract_ws_auth(websocket)
    return token


def accepted_ws_subprotocol(websocket) -> str | None:
    """Return the non-sensitive protocol name to echo during WebSocket accept."""
    protocol = websocket.headers.get("sec-websocket-protocol") or ""
    protocols = [part.strip() for part in protocol.split(",") if part.strip()]
    if "aegis.v1" in protocols:
        return "aegis.v1"
    for value in protocols:
        lowered = value.lower()
        if not lowered.startswith(("bearer.", "token.")):
            return value
    return None


def _extract_ws_auth(websocket) -> tuple[str | None, str | None, str | None]:
    auth_cfg = get_auth_config()
    token = websocket.query_params.get("token")
    if token:
        if bool(auth_cfg.get("allow_query_token_for_websocket", False)):
            return token, "query", None
        return None, "query", "Query-token WebSocket authentication is disabled"
    cookie_name = str(auth_cfg.get("cookie_name") or "aegis_access_token")
    cookie_token = websocket.cookies.get(cookie_name)
    if cookie_token:
        return cookie_token, "cookie", None
    if bool(auth_cfg.get("allow_subprotocol_token_for_websocket", True)):
        protocol = websocket.headers.get("sec-websocket-protocol") or ""
        for part in protocol.split(","):
            value = part.strip()
            if value.lower().startswith("bearer."):
                return value.split(".", 1)[1].strip() or None, "subprotocol", None
            if value.lower().startswith("token."):
                return value.split(".", 1)[1].strip() or None, "subprotocol", None
    return None, None, None


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

    token, token_source, extraction_error = _extract_ws_auth(websocket)
    if extraction_error:
        await _deny(websocket, None, extraction_error, permissions, token_source=token_source)
        return None
    if not token:
        await _deny(websocket, None, "Authentication required", permissions, token_source=token_source)
        return None

    user = get_auth_service().get_current_user_from_token(token)
    if user is None:
        await _deny(websocket, None, "Invalid or expired token", permissions, token_source=token_source)
        return None
    if user.status != UserStatus.ACTIVE.value:
        await _deny(websocket, user, "User account is not active", permissions, token_source=token_source)
        return None
    if permissions and not any(has_permission(user.role, permission, get_rbac_config()) for permission in permissions):
        await _deny(websocket, user, "Insufficient permission", permissions, token_source=token_source)
        return None

    websocket.state.current_user = user
    _metric("websocket_auth_success")
    get_audit_log_service().record(
        AuditAction.WEBSOCKET_CONNECTED,
        user=user,
        resource_type="websocket",
        resource_id=websocket.url.path,
        request=websocket,
        metadata={"permissions": permissions, "token_source": token_source},
    )
    return user


def _normalize_permissions(required_permission: str | Iterable[str] | None) -> list[str]:
    if required_permission is None:
        return []
    if isinstance(required_permission, str):
        return [required_permission]
    return [str(item) for item in required_permission]


async def _deny(
    websocket: WebSocket,
    user: UserAccount | None,
    detail: str,
    permissions: list[str],
    *,
    token_source: str | None = None,
) -> None:
    _metric("websocket_auth_failed")
    get_audit_log_service().record(
        AuditAction.WEBSOCKET_DENIED,
        user=user,
        resource_type="websocket",
        resource_id=websocket.url.path,
        success=False,
        detail=detail,
        request=websocket,
        metadata={"permissions": permissions, "token_source": token_source},
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
