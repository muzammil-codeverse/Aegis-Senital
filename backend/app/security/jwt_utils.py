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
    issuer = auth_cfg.get("token_issuer")
    audience = auth_cfg.get("token_audience")
    if issuer:
        payload["iss"] = str(issuer)
    if audience:
        payload["aud"] = str(audience)
    return jwt.encode(
        payload,
        auth_cfg["_jwt_secret"],
        algorithm=str(auth_cfg.get("algorithm") or "HS256"),
    )


def decode_access_token(token: str) -> dict:
    auth_cfg = get_auth_config()
    decode_kwargs = {}
    if auth_cfg.get("token_audience"):
        decode_kwargs["audience"] = str(auth_cfg["token_audience"])
    if auth_cfg.get("token_issuer"):
        decode_kwargs["issuer"] = str(auth_cfg["token_issuer"])
    payload = jwt.decode(
        token,
        auth_cfg["_jwt_secret"],
        algorithms=[str(auth_cfg.get("algorithm") or "HS256")],
        **decode_kwargs,
    )
    if int(payload.get("exp", 0)) < int(time.time()):
        raise jwt.ExpiredSignatureError("Token expired")
    return payload
