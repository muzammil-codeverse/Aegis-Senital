from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import case_routes, object_authorization, streaming_routes
from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from main import app


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
        "scoped-camera": _user(metadata={"camera_scopes": ["cam_01"], "case_scopes": ["case_01"]}),
        "other-camera": _user(metadata={"camera_scopes": ["cam_02"]}),
        "scoped-case": _user(role="analyst", metadata={"case_scopes": ["case_01"]}),
        "admin": _user(role="admin"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


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


def test_camera_frame_requires_scope_and_sets_sensitive_headers(monkeypatch):
    _install_auth(monkeypatch)
    frame_dir = Path("storage/frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / "security-test-latest.jpg"
    frame_path.write_bytes(b"\xff\xd8\xffframe")

    import app.core.security as frame_security
    import app.services.frame_snapshot_service as snapshot_module

    monkeypatch.setattr(frame_security, "_ALLOWED_ROOTS", [frame_dir.resolve()])
    monkeypatch.setattr(
        snapshot_module,
        "get_frame_snapshot_service",
        lambda: SimpleNamespace(get_latest_frame=lambda camera_id: {"status": "ok", "frame_path": frame_path.name}),
    )

    try:
        client = TestClient(app, raise_server_exceptions=False)

        denied = client.get("/api/cameras/cam_01/latest-frame/image", headers={"Authorization": "Bearer other-camera"})
        allowed = client.get("/api/cameras/cam_01/latest-frame/image", headers={"Authorization": "Bearer scoped-camera"})

        assert denied.status_code == 403
        assert allowed.status_code == 200
        assert allowed.headers["Cache-Control"] == "no-store"
        assert allowed.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        frame_path.unlink(missing_ok=True)


def test_hls_and_replay_path_traversal_are_rejected():
    request = _request("/api/streams/cam_01/hls/../secret.ts")
    user = _user(metadata={"camera_scopes": ["cam_01"]})

    with pytest.raises(HTTPException) as hls_exc:
        streaming_routes.stream_hls_segment_api("cam_01", "../secret.ts", request, user)
    assert hls_exc.value.status_code == 400

    with pytest.raises(HTTPException) as replay_exc:
        streaming_routes.stream_replay_get_api("cam_01", "../clip", request, user)
    assert replay_exc.value.status_code == 400


def test_case_export_requires_case_scope(monkeypatch):
    _install_auth(monkeypatch)
    case = SimpleNamespace(case_id="case_01", assigned_to=None, camera_ids=[], model_dump=lambda mode="json": {"case_id": "case_01"})
    export = SimpleNamespace(model_dump=lambda mode="json": {"case_id": "case_01", "format": "json"})
    service = SimpleNamespace(
        get_case=lambda case_id: case if case_id == "case_01" else None,
        export_case=lambda case_id, format="json", actor="system": export,
        list_cases=lambda _filters: [],
        list_evidence=lambda _case_id: [],
    )
    monkeypatch.setattr(case_routes, "get_case_service", lambda: service)
    monkeypatch.setattr(object_authorization, "get_case_service", lambda: service)

    client = TestClient(app, raise_server_exceptions=False)

    denied = client.get("/api/cases/case_01/export", headers={"Authorization": "Bearer other-camera"})
    allowed = client.get("/api/cases/case_01/export", headers={"Authorization": "Bearer scoped-case"})

    assert denied.status_code == 403
    assert allowed.status_code == 200
