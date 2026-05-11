from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import case_routes, object_authorization
from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from main import app


class AuditStub:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, action, **kwargs):
        self.entries.append({"action": getattr(action, "value", action), **kwargs})
        return None


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def _user(role: str = "operator", metadata: dict | None = None) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata=metadata or {},
    )


def _install_auth(monkeypatch):
    users = {
        "scoped": _user(role="analyst", metadata={"case_scopes": ["case_01"], "camera_scopes": ["cam_01"]}),
        "denied": _user(metadata={"camera_scopes": ["cam_02"]}),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_denied_object_access_is_audited(monkeypatch):
    audit = AuditStub()
    monkeypatch.setattr(object_authorization, "get_audit_log_service", lambda: audit)

    with pytest.raises(HTTPException):
        object_authorization.ensure_camera_access(
            _request("/api/cameras/cam_01"),
            _user(metadata={"camera_scopes": ["cam_02"]}),
            "cam_01",
        )

    assert any(entry["action"] == "access_denied" for entry in audit.entries)


def test_case_export_is_audited(monkeypatch):
    _install_auth(monkeypatch)
    audit = AuditStub()
    case = SimpleNamespace(case_id="case_01", assigned_to=None, camera_ids=[], model_dump=lambda mode="json": {"case_id": "case_01"})
    export = SimpleNamespace(model_dump=lambda mode="json": {"case_id": "case_01", "format": "json"})
    service = SimpleNamespace(
        get_case=lambda case_id: case if case_id == "case_01" else None,
        export_case=lambda case_id, format="json", actor="system": export,
        list_cases=lambda _filters: [],
        list_evidence=lambda _case_id: [],
    )
    monkeypatch.setattr(case_routes, "get_case_service", lambda: service)
    monkeypatch.setattr(case_routes, "get_audit_log_service", lambda: audit)
    monkeypatch.setattr(object_authorization, "get_case_service", lambda: service)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/cases/case_01/export", headers={"Authorization": "Bearer scoped"})

    assert response.status_code == 200
    assert any(entry["action"] == "case_exported" for entry in audit.entries)
