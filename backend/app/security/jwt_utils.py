from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt

from app.models.security_models import UserAccount
from app.security.config import get_auth_config


def create_access_token(user: UserAccount, expires_minutes: int) -> str:
    auth_cfg = get_auth_config()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=int(expires_minutes))
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(
        payload,
        auth_cfg["_jwt_secret"],
        algorithm=str(auth_cfg.get("algorithm") or "HS256"),
    )


def decode_access_token(token: str) -> dict:
    auth_cfg = get_auth_config()
    payload = jwt.decode(
        token,
        auth_cfg["_jwt_secret"],
        algorithms=[str(auth_cfg.get("algorithm") or "HS256")],
    )
    if int(payload.get("exp", 0)) < int(time.time()):
        raise jwt.ExpiredSignatureError("Token expired")
    return payload
