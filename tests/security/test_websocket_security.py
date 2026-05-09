import asyncio
from types import SimpleNamespace

from app.api import websocket_security
from app.api.websocket_security import authenticate_websocket, extract_ws_token
from app.models.security_models import UserAccount


class DummyWebSocket:
    def __init__(self, token=None):
        self.query_params = {"token": token} if token else {}
        self.cookies = {}
        self.headers = {}
        self.state = SimpleNamespace()
        self.url = SimpleNamespace(path="/ws/alerts")
        self.client = SimpleNamespace(host="127.0.0.1")
        self.closed = None

    async def close(self, code=1000, reason=None):
        self.closed = (code, reason)


class AuditStub:
    def record(self, *args, **kwargs):
        return None


def _user(role="admin"):
    return UserAccount(
        user_id="u1",
        username="admin",
        display_name="Admin",
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def test_token_extraction_from_query_param():
    websocket = DummyWebSocket(token="abc")
    assert extract_ws_token(websocket) == "abc"


def test_missing_token_fails_when_auth_required(monkeypatch):
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: AuditStub())
    websocket = DummyWebSocket()
    result = asyncio.run(authenticate_websocket(websocket, "alert:read"))
    assert result is None
    assert websocket.closed[0] == 1008


def test_invalid_token_fails(monkeypatch):
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: AuditStub())
    monkeypatch.setattr(
        websocket_security,
        "get_auth_service",
        lambda: SimpleNamespace(get_current_user_from_token=lambda token: None),
    )
    websocket = DummyWebSocket(token="bad")
    result = asyncio.run(authenticate_websocket(websocket, "alert:read"))
    assert result is None
    assert websocket.closed[0] == 1008


def test_valid_token_attaches_user(monkeypatch):
    user = _user("admin")
    monkeypatch.setattr(websocket_security, "auth_required", lambda: True)
    monkeypatch.setattr(websocket_security, "get_audit_log_service", lambda: AuditStub())
    monkeypatch.setattr(
        websocket_security,
        "get_auth_service",
        lambda: SimpleNamespace(get_current_user_from_token=lambda token: user),
    )
    websocket = DummyWebSocket(token="ok")
    result = asyncio.run(authenticate_websocket(websocket, "alert:read"))
    assert result is user
    assert websocket.state.current_user is user
