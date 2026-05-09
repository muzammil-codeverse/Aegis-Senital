from __future__ import annotations

import logging
from typing import Any

from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.security.config import get_auth_config, get_rbac_config
from app.security.jwt_utils import create_access_token, decode_access_token
from app.security.permissions import permissions_for_role
from app.services.audit_log_service import get_audit_log_service
from app.services.user_store import get_user_store

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self) -> None:
        self._users = get_user_store()
        self._audit = get_audit_log_service()

    def bootstrap(self) -> None:
        self._users.bootstrap_admin_if_empty()

    def login(self, username: str, password: str, request: Any = None) -> dict:
        self._users.unlock_expired_users()
        user = self._users.get_user_by_username(username)
        if user is None or user.status != UserStatus.ACTIVE.value:
            if user is not None and user.status == UserStatus.LOCKED.value:
                detail = "User is locked"
            elif user is not None and user.status == UserStatus.DISABLED.value:
                detail = "User is disabled"
            else:
                detail = "Invalid credentials"
            self._users.record_login_failure(username)
            self._audit.record(
                AuditAction.LOGIN_FAILED,
                user=user,
                resource_type="auth",
                success=False,
                detail=detail,
                request=request,
                metadata={"username": username},
            )
            try:
                from inference.metrics import metrics
                metrics.increment("auth_logins_failed")
            except Exception:
                pass
            raise AuthError("Invalid username or password")

        authenticated = self._users.authenticate(username, password)
        if authenticated is None:
            self._audit.record(
                AuditAction.LOGIN_FAILED,
                user=user,
                resource_type="auth",
                success=False,
                detail="Invalid credentials",
                request=request,
                metadata={"username": username},
            )
            try:
                from inference.metrics import metrics
                metrics.increment("auth_logins_failed")
            except Exception:
                pass
            raise AuthError("Invalid username or password")

        auth_cfg = get_auth_config()
        expires_minutes = int(auth_cfg.get("access_token_minutes", 480))
        token = create_access_token(authenticated, expires_minutes)
        self._audit.record(
            AuditAction.LOGIN_SUCCESS,
            user=authenticated,
            resource_type="auth",
            success=True,
            request=request,
        )
        try:
            from inference.metrics import metrics
            metrics.increment("auth_logins_success")
        except Exception:
            pass

        permissions = permissions_for_role(authenticated.role, get_rbac_config())
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": authenticated.to_dict(),
            "permissions": permissions,
            "expires_in_seconds": expires_minutes * 60,
        }

    def get_current_user_from_token(self, token: str) -> UserAccount | None:
        try:
            payload = decode_access_token(token)
        except Exception:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = self._users.get_user(str(user_id))
        if user is None:
            return None
        if user.status != UserStatus.ACTIVE.value:
            return None
        return user

    def logout(self, user: UserAccount | None, request: Any = None) -> dict:
        self._audit.record(
            AuditAction.LOGOUT,
            user=user,
            resource_type="auth",
            success=True,
            request=request,
        )
        return {"status": "ok"}

    def create_user(self, username: str, password: str, **kwargs) -> UserAccount:
        user = self._users.create_user(username=username, password=password, **kwargs)
        return user

    def update_user(self, user_id: str, updates: dict) -> UserAccount | None:
        return self._users.update_user(user_id, updates)

    def list_users(self, **kwargs) -> list[UserAccount]:
        return self._users.list_users(**kwargs)

    def get_user(self, user_id: str) -> UserAccount | None:
        return self._users.get_user(user_id)

    def disable_user(self, user_id: str) -> UserAccount | None:
        return self._users.disable_user(user_id)

    def lock_user(self, user_id: str) -> UserAccount | None:
        return self._users.lock_user(user_id)


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
