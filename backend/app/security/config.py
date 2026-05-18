from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.env_loader import load_project_env

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SECURITY_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "security.yaml"
UPLOAD_SECURITY_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "upload_security.yaml"
PRODUCTION_ENVS = {"prod", "production"}
_DEV_JWT_SECRET: str | None = None
_DEV_SECRET_FILE = PROJECT_ROOT / ".dev_jwt_secret"

load_project_env()


def _environment_name() -> str:
    return (os.getenv("AEGIS_ENV") or os.getenv("APP_ENV") or "dev").strip().lower()


def environment_name() -> str:
    return _environment_name()


def is_production_environment() -> bool:
    return _environment_name() in PRODUCTION_ENVS


@lru_cache(maxsize=1)
def load_security_config() -> dict[str, Any]:
    if not SECURITY_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Security config not found: {SECURITY_CONFIG_PATH}")
    with SECURITY_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid security config: {SECURITY_CONFIG_PATH}")
    _resolve_jwt_secret(data)
    return data


def _resolve_jwt_secret(config: dict[str, Any]) -> str:
    global _DEV_JWT_SECRET
    auth_cfg = config.setdefault("auth", {})
    secret_env = str(auth_cfg.get("jwt_secret_env") or "AEGIS_JWT_SECRET")
    secret = os.getenv(secret_env)
    if secret:
        auth_cfg["_jwt_secret"] = secret
        return secret

    if _environment_name() in PRODUCTION_ENVS and bool(auth_cfg.get("require_auth", True)):
        raise RuntimeError(
            f"{secret_env} is required when auth.require_auth is true in production"
        )

    if _DEV_JWT_SECRET is None:
        _DEV_JWT_SECRET = _load_or_create_dev_secret(secret_env)
    auth_cfg["_jwt_secret"] = _DEV_JWT_SECRET
    return _DEV_JWT_SECRET


def _load_or_create_dev_secret(secret_env: str) -> str:
    try:
        if _DEV_SECRET_FILE.exists():
            stored = _DEV_SECRET_FILE.read_text(encoding="utf-8").strip()
            if stored:
                logger.info(
                    "%s is not set; reusing persistent dev JWT secret from %s",
                    secret_env,
                    _DEV_SECRET_FILE.name,
                )
                return stored
    except OSError:
        pass
    new_secret = secrets.token_urlsafe(48)
    try:
        _DEV_SECRET_FILE.write_text(new_secret, encoding="utf-8")
        logger.warning(
            "%s is not set; generated a persistent dev JWT secret at %s "
            "(sessions survive restarts; set %s for production)",
            secret_env,
            _DEV_SECRET_FILE.name,
            secret_env,
        )
    except OSError:
        logger.warning(
            "%s is not set; using an ephemeral dev JWT secret "
            "(could not persist to %s — all sessions invalidated on restart)",
            secret_env,
            _DEV_SECRET_FILE.name,
        )
    return new_secret


def get_auth_config() -> dict[str, Any]:
    auth_cfg = dict(load_security_config().get("auth") or {})
    if is_production_environment():
        if bool(auth_cfg.get("set_auth_cookie", True)):
            auth_cfg["cookie_secure"] = True
        auth_cfg["allow_query_token_for_websocket"] = False
        auth_cfg["expose_bearer_response"] = False
    else:
        auth_cfg["allow_query_token_for_websocket"] = bool(auth_cfg.get("allow_query_token_for_websocket", False))
        auth_cfg["expose_bearer_response"] = bool(auth_cfg.get("expose_bearer_response", True))
    auth_cfg["allow_subprotocol_token_for_websocket"] = bool(
        auth_cfg.get("allow_subprotocol_token_for_websocket", True)
    )
    auth_cfg["cookie_path"] = str(auth_cfg.get("cookie_path") or "/")
    auth_cfg["csrf_cookie_name"] = str(auth_cfg.get("csrf_cookie_name") or "aegis_csrf_token")
    auth_cfg["csrf_header_name"] = str(auth_cfg.get("csrf_header_name") or "X-CSRF-Token")
    auth_cfg["csrf_protect_cookie_auth"] = bool(auth_cfg.get("csrf_protect_cookie_auth", True))
    return auth_cfg


def get_password_config() -> dict[str, Any]:
    return dict(load_security_config().get("password") or {})


def get_lockout_config() -> dict[str, Any]:
    return dict(load_security_config().get("lockout") or {})


def get_rate_limit_config() -> dict[str, Any]:
    return dict(load_security_config().get("rate_limit") or {})


def get_audit_config() -> dict[str, Any]:
    return dict(load_security_config().get("audit") or {})


def get_privacy_config() -> dict[str, Any]:
    return dict(load_security_config().get("privacy") or {})


def get_rbac_config() -> dict[str, list[str]]:
    return dict(load_security_config().get("rbac") or {})


def get_mfa_config() -> dict[str, Any]:
    return dict(load_security_config().get("mfa") or {})


def get_upload_security_config() -> dict[str, Any]:
    if not UPLOAD_SECURITY_CONFIG_PATH.exists():
        return {}
    with UPLOAD_SECURITY_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid upload security config: {UPLOAD_SECURITY_CONFIG_PATH}")
    return data


def auth_required() -> bool:
    return bool(get_auth_config().get("require_auth", True))


def project_path(relative_path: str) -> Path:
    return (PROJECT_ROOT / relative_path).resolve()
