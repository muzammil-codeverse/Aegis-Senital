from __future__ import annotations

import logging
from typing import Any

from app.models.security_models import AuditAction, UserAccount, UserStatus
from app.security.config import get_auth_config, get_rate_limit_config, get_rbac_config
from app.security.jwt_utils import create_access_token, decode_access_token
from app.security.mfa import mfa_status_for_user
from app.security.permissions import permissions_for_role
from app.security.rate_limiter import login_rate_limiter
from app.services.audit_log_service import get_audit_log_service
from app.services.user_store import get_user_store

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


class AuthRateLimitError(Exception):
    pass


class AuthService:
    def __init__(self) -> None:
        self._users = get_user_store()
        self._audit = get_audit_log_service()

    def bootstrap(self) -> None:
        self._users.bootstrap_admin_if_empty()

    def login(self, username: str, password: str, request: Any = None) -> dict:
        self._users.unlock_expired_users()
        self._enforce_login_rate_limit(username, request)
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

        mfa_status = mfa_status_for_user(authenticated)
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
        self._reset_login_rate_limit(username, request)

        permissions = permissions_for_role(authenticated.role, get_rbac_config())
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": authenticated.to_dict(),
            "permissions": permissions,
            "mfa_status": mfa_status.value,
            "expires_in_seconds": expires_minutes * 60,
        }

    def _enforce_login_rate_limit(self, username: str, request: Any = None) -> None:
        cfg = get_rate_limit_config()
        ip_limit = int(cfg.get("login_attempts_per_minute", 5))
        user_limit = int(cfg.get("login_attempts_per_username_per_minute", 5))
        window = 60
        ip = self._request_ip(request)
        normalized_user = (username or "").strip().lower() or "unknown"
        keys = [
            (f"ip:{ip}", ip_limit),
            (f"user:{normalized_user}", user_limit),
            (f"combo:{ip}:{normalized_user}", min(ip_limit, user_limit)),
        ]
        for key, limit in keys:
            if not login_rate_limiter.allow(key, limit, window):
                self._audit.record(
                    AuditAction.LOGIN_FAILED,
                    resource_type="auth",
                    success=False,
                    detail="Too many login attempts",
                    request=request,
                    metadata={"rate_limited": True, "username": normalized_user},
                )
                try:
                    from inference.metrics import metrics
                    metrics.increment("auth_rate_limited")
                except Exception:
                    pass
                raise AuthRateLimitError("Too many login attempts")

    def _reset_login_rate_limit(self, username: str, request: Any = None) -> None:
        ip = self._request_ip(request)
        normalized_user = (username or "").strip().lower() or "unknown"
        for key in (f"ip:{ip}", f"user:{normalized_user}", f"combo:{ip}:{normalized_user}"):
            login_rate_limiter.reset(key)

    @staticmethod
    def _request_ip(request: Any = None) -> str:
        if request is None:
            return "unknown"
        forwarded = request.headers.get("x-forwarded-for") if hasattr(request, "headers") else None
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or "unknown"
        client = getattr(request, "client", None)
        return getattr(client, "host", None) or "unknown"

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

    def change_password(
        self,
        user: UserAccount,
        current_password: str,
        new_password: str,
        request: Any = None,
    ) -> UserAccount:
        try:
            updated = self._users.change_password(user.user_id, current_password, new_password)
        except PermissionError:
            self._audit.record(
                AuditAction.PASSWORD_CHANGED,
                user=user,
                resource_type="user",
                resource_id=user.user_id,
                success=False,
                detail="Password change failed",
                request=request,
            )
            raise AuthError("Current password is invalid")
        except ValueError:
            self._audit.record(
                AuditAction.PASSWORD_CHANGED,
                user=user,
                resource_type="user",
                resource_id=user.user_id,
                success=False,
                detail="Password strength validation failed",
                request=request,
            )
            raise
        if updated is None:
            raise AuthError("User not found")
        self._audit.record(
            AuditAction.PASSWORD_CHANGED,
            user=updated,
            resource_type="user",
            resource_id=updated.user_id,
            success=True,
            request=request,
        )
        try:
            from inference.metrics import metrics
            metrics.increment("password_changes")
        except Exception:
            pass
        return updated

    def reset_password_by_admin(
        self,
        admin_user: UserAccount,
        user_id: str,
        new_password: str,
        must_change_password: bool = True,
        request: Any = None,
    ) -> UserAccount | None:
        try:
            user = self._users.reset_password(user_id, new_password, must_change_password=must_change_password)
        except ValueError:
            self._audit.record(
                AuditAction.PASSWORD_RESET,
                user=admin_user,
                resource_type="user",
                resource_id=user_id,
                success=False,
                detail="Password strength validation failed",
                request=request,
                metadata={"must_change_password": bool(must_change_password)},
            )
            raise
        self._audit.record(
            AuditAction.PASSWORD_RESET,
            user=admin_user,
            resource_type="user",
            resource_id=user_id,
            success=user is not None,
            detail="Admin password reset" if user is not None else "Admin password reset failed",
            request=request,
            metadata={"must_change_password": bool(must_change_password)},
        )
        if user is not None:
            try:
                from inference.metrics import metrics
                metrics.increment("password_reset_by_admin")
            except Exception:
                pass
        return user


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
