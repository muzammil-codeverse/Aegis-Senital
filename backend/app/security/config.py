from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SECURITY_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "security.yaml"
PRODUCTION_ENVS = {"prod", "production"}
_DEV_JWT_SECRET: str | None = None

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / "backend" / ".env")
except Exception:
    pass


def _environment_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "dev").strip().lower()


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
        _DEV_JWT_SECRET = secrets.token_urlsafe(48)
        logger.warning(
            "%s is not set; using an ephemeral local development JWT secret",
            secret_env,
        )
    auth_cfg["_jwt_secret"] = _DEV_JWT_SECRET
    return _DEV_JWT_SECRET


def get_auth_config() -> dict[str, Any]:
    return dict(load_security_config().get("auth") or {})


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


def auth_required() -> bool:
    return bool(get_auth_config().get("require_auth", True))


def project_path(relative_path: str) -> Path:
    return (PROJECT_ROOT / relative_path).resolve()
