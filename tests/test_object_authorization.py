from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import object_authorization as authz
from app.models.security_models import UserAccount


class AuditStub:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def record(self, action, **kwargs):
        self.entries.append({"action": getattr(action, "value", action), **kwargs})
        return None


def _request(path: str = "/api/cameras/cam_01") -> Request:
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


def test_camera_scope_denies_user_without_scope():
    assert authz.can_access_camera(_user(metadata={"camera_scopes": ["cam_01"]}), "cam_02") is False


def test_camera_scope_allows_user_with_scope():
    assert authz.can_access_camera(_user(metadata={"camera_scopes": ["cam_01"]}), "cam_01") is True


def test_case_scope_can_be_derived_from_camera_scope(monkeypatch):
    case_service = SimpleNamespace(
        get_case=lambda case_id: SimpleNamespace(case_id=case_id, assigned_to=None, camera_ids=["cam_01"]),
        list_cases=lambda _filters: [],
        list_evidence=lambda _case_id: [],
    )
    monkeypatch.setattr(authz, "get_case_service", lambda: case_service)

    user = _user(metadata={"camera_scopes": ["cam_01"]})
    assert authz.can_access_case(user, "case_123") is True


def test_admin_bypass_is_explicit_and_audited(monkeypatch):
    audit = AuditStub()
    monkeypatch.setattr(authz, "get_audit_log_service", lambda: audit)

    request = _request()
    admin = _user(role="admin")
    authz.ensure_camera_access(request, admin, "cam_secret")

    assert any(entry["action"] == "object_access_bypass" for entry in audit.entries)


def test_denied_object_access_raises_403_and_audits(monkeypatch):
    audit = AuditStub()
    monkeypatch.setattr(authz, "get_audit_log_service", lambda: audit)

    request = _request("/api/cases/case_999")
    with pytest.raises(HTTPException) as excinfo:
        authz.ensure_camera_access(request, _user(metadata={"camera_scopes": ["cam_01"]}), "cam_02")

    assert excinfo.value.status_code == 403
    assert any(entry["action"] == "access_denied" for entry in audit.entries)
