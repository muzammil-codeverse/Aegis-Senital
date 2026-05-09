from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.models.security_models import UserAccount, UserRole, UserStatus, sanitize_metadata
from app.security.config import (
    get_auth_config,
    get_lockout_config,
    get_password_config,
    project_path,
)
from app.security.password_utils import (
    hash_password,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger(__name__)


class UserStore:
    def __init__(self, storage_path: str | None = None) -> None:
        self._lock = threading.RLock()
        path = storage_path or str(project_path("storage/security/users.jsonl"))
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._users: dict[str, UserAccount] = {}
        self._by_username: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            self._users.clear()
            self._by_username.clear()
            if not self._path.exists():
                return
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        user = UserAccount.from_dict(json.loads(line))
                    except Exception as exc:
                        logger.warning("Failed to load user record: %s", exc)
                        continue
                    self._users[user.user_id] = user
                    self._by_username[self._normalize_username(user.username)] = user.user_id

    def _append(self, user: UserAccount) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(user.to_record(), sort_keys=True) + "\n")

    def _rewrite(self) -> None:
        tmp = self._path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for user in self._users.values():
                fh.write(json.dumps(user.to_record(), sort_keys=True) + "\n")
        tmp.replace(self._path)

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.strip().lower()

    @staticmethod
    def _validate_role(role: str) -> str:
        role_value = str(role or UserRole.VIEWER.value).lower()
        allowed = {item.value for item in UserRole}
        if role_value not in allowed:
            raise ValueError(f"Invalid role: {role}")
        return role_value

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        role: str = "viewer",
        metadata: dict | None = None,
    ) -> UserAccount:
        username = username.strip()
        if not username:
            raise ValueError("Username is required")
        role = self._validate_role(role)
        ok, errors = validate_password_strength(password, get_password_config())
        if not ok:
            raise ValueError("; ".join(errors))

        now = time.time()
        with self._lock:
            normalized = self._normalize_username(username)
            if normalized in self._by_username:
                raise ValueError("Username already exists")
            user = UserAccount(
                user_id=str(uuid.uuid4()),
                username=username,
                display_name=display_name,
                role=role,
                status=UserStatus.ACTIVE.value,
                password_hash=hash_password(password),
                created_at=now,
                updated_at=now,
                metadata=sanitize_metadata(metadata or {}),
            )
            self._users[user.user_id] = user
            self._by_username[normalized] = user.user_id
            self._append(user)
            return user

    def authenticate(self, username: str, password: str) -> UserAccount | None:
        user = self.get_user_by_username(username)
        if user is None:
            self.record_login_failure(username)
            return None
        if user.status != UserStatus.ACTIVE.value:
            return None
        if not verify_password(password, user.password_hash):
            self.record_login_failure(username)
            return None
        self.record_login_success(user.user_id)
        return self.get_user(user.user_id)

    def get_user(self, user_id: str) -> UserAccount | None:
        with self._lock:
            return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> UserAccount | None:
        with self._lock:
            user_id = self._by_username.get(self._normalize_username(username))
            return self._users.get(user_id) if user_id else None

    def list_users(
        self,
        role: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[UserAccount]:
        with self._lock:
            users = list(self._users.values())
        if role:
            users = [user for user in users if user.role == role]
        if status:
            users = [user for user in users if user.status == status]
        users.sort(key=lambda user: user.created_at)
        return users[: max(1, int(limit))]

    def update_user(self, user_id: str, updates: dict[str, Any]) -> UserAccount | None:
        allowed = {"display_name", "role", "status", "metadata", "password"}
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return None
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key == "role":
                    user.role = self._validate_role(str(value))
                elif key == "status":
                    status_value = str(value).lower()
                    if status_value not in {item.value for item in UserStatus}:
                        raise ValueError(f"Invalid status: {value}")
                    user.status = status_value
                elif key == "metadata":
                    user.metadata = sanitize_metadata(value or {})
                elif key == "password":
                    ok, errors = validate_password_strength(str(value), get_password_config())
                    if not ok:
                        raise ValueError("; ".join(errors))
                    user.password_hash = hash_password(str(value))
                else:
                    setattr(user, key, value)
            user.updated_at = time.time()
            self._rewrite()
            return user

    def disable_user(self, user_id: str) -> UserAccount | None:
        return self.update_user(user_id, {"status": UserStatus.DISABLED.value})

    def lock_user(self, user_id: str) -> UserAccount | None:
        return self.update_user(user_id, {"status": UserStatus.LOCKED.value})

    def record_login_success(self, user_id: str) -> None:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return
            user.failed_login_count = 0
            user.last_login_at = time.time()
            user.updated_at = user.last_login_at
            self._rewrite()

    def record_login_failure(self, username: str) -> None:
        lockout_cfg = get_lockout_config()
        with self._lock:
            user = self.get_user_by_username(username)
            if user is None:
                return
            user.failed_login_count += 1
            user.updated_at = time.time()
            if bool(lockout_cfg.get("enabled", True)):
                max_failed = int(lockout_cfg.get("max_failed_attempts", 5))
                if user.failed_login_count >= max_failed:
                    user.status = UserStatus.LOCKED.value
                    user.metadata = dict(user.metadata or {})
                    user.metadata["locked_at"] = time.time()
                    user.metadata["lockout_seconds"] = int(lockout_cfg.get("lockout_seconds", 900))
            self._rewrite()

    def unlock_expired_users(self) -> None:
        lockout_cfg = get_lockout_config()
        if not bool(lockout_cfg.get("enabled", True)):
            return
        lockout_seconds = int(lockout_cfg.get("lockout_seconds", 900))
        now = time.time()
        changed = False
        with self._lock:
            for user in self._users.values():
                if user.status != UserStatus.LOCKED.value:
                    continue
                locked_at = float((user.metadata or {}).get("locked_at") or 0)
                if locked_at and now - locked_at >= lockout_seconds:
                    user.status = UserStatus.ACTIVE.value
                    user.failed_login_count = 0
                    user.metadata.pop("locked_at", None)
                    user.updated_at = now
                    changed = True
            if changed:
                self._rewrite()

    def bootstrap_admin_if_empty(self) -> UserAccount | None:
        with self._lock:
            if self._users:
                return None

        auth_cfg = get_auth_config()
        username = str(auth_cfg.get("bootstrap_admin_username") or "admin")
        password_env = str(auth_cfg.get("bootstrap_admin_password_env") or "AEGIS_BOOTSTRAP_ADMIN_PASSWORD")
        password = os.getenv(password_env)
        if not password:
            env_name = (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "dev").lower()
            if env_name in {"prod", "production"}:
                logger.warning("Bootstrap admin skipped: %s is not set", password_env)
                return None
            password = "ChangeMe123"
            logger.warning(
                "Bootstrap admin using local development fallback password; set %s for real deployments",
                password_env,
            )

        try:
            return self.create_user(
                username=username,
                password=password,
                display_name="System Administrator",
                role=UserRole.ADMIN.value,
                metadata={"bootstrap": True},
            )
        except ValueError as exc:
            logger.warning("Bootstrap admin skipped: %s", exc)
            return None

    def counts(self) -> dict[str, int]:
        with self._lock:
            users = list(self._users.values())
        return {
            "users_total": len(users),
            "users_active": sum(1 for user in users if user.status == UserStatus.ACTIVE.value),
            "users_locked": sum(1 for user in users if user.status == UserStatus.LOCKED.value),
            "users_disabled": sum(1 for user in users if user.status == UserStatus.DISABLED.value),
        }


_user_store: UserStore | None = None
_user_store_lock = threading.Lock()


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        with _user_store_lock:
            if _user_store is None:
                _user_store = UserStore()
    return _user_store
