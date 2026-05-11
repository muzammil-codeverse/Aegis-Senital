from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api import websocket_security
from app.api.websocket_security import authenticate_websocket
from app.models.security_models import UserAccount


class DummyWebSocket:
    def __init__(self, *, token: str | None = None, protocols: str = "") -> None:
        self.query_params = {"token": token} if token else {}
        self.cookies = {}
        self.headers = {"sec-websocket-protocol": protocols} if protocols else {}
        self.state = SimpleNamespace()
        self.url = SimpleNamespace(path="/ws/open-vocab")
        self.client = SimpleNamespace(host="127.0.0.1")
        self.closed = None

    async def close(self, code=1000, reason=None):
        self.closed = (code, reason)


class AuditStub:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, action, **kwargs):
        self.entries.append({"action": getattr(action, "value", action), **kwargs})
        return None


def _user(role: str = "supervisor") -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def test_query_token_is_rejected_when_disabled(monkeypatch):
    audit = AuditStub()
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(
        websocket_security,
        "get_auth_config",
        lambda: {
            "allow_query_token_for_websocket": False,
            "allow_subprotocol_token_for_websocket": True,
            "cookie_name": "aegis_access_token",
        },
    )
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: audit)

    websocket = DummyWebSocket(token="query-token")
    result = asyncio.run(authenticate_websocket(websocket, "open_vocab:read"))

    assert result is None
    assert websocket.closed[0] == 1008
    assert "disabled" in (websocket.closed[1] or "").lower()
    assert any(entry["action"] == "websocket_denied" for entry in audit.entries)


def test_dev_query_token_mode_can_be_enabled_explicitly(monkeypatch):
    user = _user()
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(
        websocket_security,
        "get_auth_config",
        lambda: {
            "allow_query_token_for_websocket": True,
            "allow_subprotocol_token_for_websocket": True,
            "cookie_name": "aegis_access_token",
        },
    )
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: AuditStub())
    monkeypatch.setattr(
        websocket_security,
        "get_auth_service",
        lambda: SimpleNamespace(get_current_user_from_token=lambda token: user if token == "query-token" else None),
    )

    websocket = DummyWebSocket(token="query-token")
    result = asyncio.run(authenticate_websocket(websocket, "open_vocab:read"))

    assert result is user


def test_subprotocol_token_is_preferred_non_query_transport(monkeypatch):
    user = _user()
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(
        websocket_security,
        "get_auth_config",
        lambda: {
            "allow_query_token_for_websocket": False,
            "allow_subprotocol_token_for_websocket": True,
            "cookie_name": "aegis_access_token",
        },
    )
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: AuditStub())
    monkeypatch.setattr(
        websocket_security,
        "get_auth_service",
        lambda: SimpleNamespace(get_current_user_from_token=lambda token: user if token == "subprotocol-token" else None),
    )

    websocket = DummyWebSocket(protocols="aegis.v1, token.subprotocol-token")
    result = asyncio.run(authenticate_websocket(websocket, "open_vocab:read"))

    assert result is user
