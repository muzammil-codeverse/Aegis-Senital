from __future__ import annotations

import re

import bcrypt

from app.security.config import get_password_config


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")
    rounds = int(get_password_config().get("bcrypt_rounds", 12))
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str, policy: dict) -> tuple[bool, list[str]]:
    errors: list[str] = []
    min_length = int(policy.get("min_length", 10))
    if len(password or "") < min_length:
        errors.append(f"Password must be at least {min_length} characters")
    if policy.get("require_uppercase", True) and not re.search(r"[A-Z]", password or ""):
        errors.append("Password must include an uppercase letter")
    if policy.get("require_lowercase", True) and not re.search(r"[a-z]", password or ""):
        errors.append("Password must include a lowercase letter")
    if policy.get("require_number", True) and not re.search(r"\d", password or ""):
        errors.append("Password must include a number")
    if policy.get("require_symbol", False) and not re.search(r"[^A-Za-z0-9]", password or ""):
        errors.append("Password must include a symbol")
    return not errors, errors
