from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.security_dependencies import permission_for_request
from app.models.security_models import UserAccount
from app.services import auth_service as auth_module
from main import app


def _user(role: str) -> UserAccount:
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


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "analyst": _user("analyst"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_sensitive_routes_have_explicit_permission_mapping():
    expected = {
        ("GET", "/api/cameras/cam_01/latest-frame"): "camera:read",
        ("POST", "/api/cameras/cam_01/control"): "camera:control",
        ("GET", "/api/streams/cam_01/hls/playlist.m3u8"): "stream:read",
        ("POST", "/api/streams/cam_01/replay/export"): "stream:replay",
        ("GET", "/api/cases/case_01/export"): "case:export",
        ("GET", "/api/cases/case_01/evidence/manifest"): "case:export",
        ("POST", "/api/cases/case_01/evidence/upload"): "case:write",
        ("GET", "/api/cases/case_01/evidence/evd_01/download"): "case:read",
        ("POST", "/api/cases/case_01/evidence/evd_01/verify"): "case:read",
        ("POST", "/api/cases/case_01/enrichment/upload"): "osint:write",
        ("GET", "/api/cases/case_01/enrichment/sources/src_01/download"): "osint:read",
        ("GET", "/api/identity/enrollments/abc"): "identity:read",
        ("POST", "/api/open-vocab/model/load"): "open_vocab:model",
        ("GET", "/api/open-vocab/model/status"): "open_vocab:read",
        ("GET", "/api/system/health"): "system:read",
        ("GET", "/events"): "event:read",
        ("GET", "/api/alerts/alert_01"): "alert:read",
        ("POST", "/api/uploaded-videos"): "uploaded_video:write",
        ("POST", "/api/uploaded-videos/uvs_01/process"): "uploaded_video:process",
        ("GET", "/api/uploaded-videos/uvs_01/status"): "uploaded_video:read",
        ("POST", "/api/uploaded-videos/uvs_01/create-case"): "uploaded_video:case",
        ("GET", "/api/uploaded-videos/uvs_01/clips/evt_01/download"): "uploaded_video:read",
        ("GET", "/api/identity/candidates"): "identity:read",
        ("POST", "/api/identity/candidates/c1/accept"): "identity:write",
        ("GET", "/api/model-governance/registry"): "model:read",
        ("POST", "/api/model-governance/rollback"): "model:rollback",
        ("POST", "/api/model-governance/promote"): "model:approve",
        ("GET", "/api/gis/config"): "gis:read",
        ("POST", "/api/gis/geofences"): "gis:write",
        ("GET", "/api/drone-simulation/status"): "drone:read",
        ("POST", "/api/drone-simulation/start"): "drone:control",
    }
    for route_key, permission in expected.items():
        method, path = route_key
        assert permission_for_request(method, path) == permission


def test_open_vocab_model_operations_require_model_permission(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)

    analyst = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer analyst"})
    supervisor = client.post("/api/open-vocab/model/load", headers={"Authorization": "Bearer supervisor"})

    assert analyst.status_code == 403
    assert supervisor.status_code in {200, 503}
