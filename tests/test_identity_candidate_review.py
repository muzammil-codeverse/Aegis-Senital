from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import AuditAction, UserAccount
from app.repositories.identity_candidate_repository import reset_identity_candidate_repository_for_tests
from app.services import auth_service as auth_module
from app.services.audit_log_service import get_audit_log_service
from app.services.identity_candidate_service import get_identity_candidate_service, reset_identity_candidate_service_for_tests
from main import app


def _user(role: str, **meta) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata=dict(meta),
    )


def test_candidate_accept_reject_escalate_requires_write_permission(tmp_path, monkeypatch):
    store = tmp_path / "candidates.json"
    reset_identity_candidate_repository_for_tests(store)
    reset_identity_candidate_service_for_tests()

    users = {
        "viewer": _user("viewer"),
        "analyst": _user("analyst", camera_scopes=["cam_demo"]),
    }
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))

    svc = get_identity_candidate_service()
    row = svc.seed_demo_candidate({"camera_id": "cam_demo"})
    cid = row["identity_candidate_id"]

    client = TestClient(app, raise_server_exceptions=False)
    assert client.post(f"/api/identity/candidates/{cid}/accept", headers={"Authorization": "Bearer viewer"}).status_code == 403
    r = client.post(f"/api/identity/candidates/{cid}/accept", headers={"Authorization": "Bearer analyst"})
    assert r.status_code == 200


def test_candidate_review_audited(tmp_path, monkeypatch):
    store = tmp_path / "candidates.json"
    reset_identity_candidate_repository_for_tests(store)
    reset_identity_candidate_service_for_tests()

    users = {"analyst": _user("analyst", camera_scopes=["cam_x"])}
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))

    svc = get_identity_candidate_service()
    row = svc.seed_demo_candidate({"camera_id": "cam_x"})
    cid = row["identity_candidate_id"]

    captured: list = []

    def _record(action, *args, **kwargs):
        captured.append(action)

    monkeypatch.setattr(get_audit_log_service(), "record", _record)

    client = TestClient(app, raise_server_exceptions=False)
    client.post(f"/api/identity/candidates/{cid}/reject", headers={"Authorization": "Bearer analyst"}, json={})
    assert AuditAction.IDENTITY_CANDIDATE_REJECTED in captured


def test_candidate_access_respects_camera_scope(tmp_path, monkeypatch):
    store = tmp_path / "candidates.json"
    reset_identity_candidate_repository_for_tests(store)
    reset_identity_candidate_service_for_tests()

    users = {"analyst": _user("analyst", camera_scopes=["cam_allowed"])}
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))

    svc = get_identity_candidate_service()
    row = svc.seed_demo_candidate({"camera_id": "cam_denied"})
    cid = row["identity_candidate_id"]

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get(f"/api/identity/candidates/{cid}", headers={"Authorization": "Bearer analyst"})
    assert res.status_code == 403
