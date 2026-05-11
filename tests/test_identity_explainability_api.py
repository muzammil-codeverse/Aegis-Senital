from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from app.repositories.identity_candidate_repository import reset_identity_candidate_repository_for_tests
from app.services import auth_service as auth_module
from app.services.identity_candidate_service import get_identity_candidate_service, reset_identity_candidate_service_for_tests
from main import app


def _admin() -> UserAccount:
    return UserAccount(
        user_id="u-admin",
        username="admin",
        display_name="admin",
        role="admin",
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


def test_get_candidate_includes_explainability(tmp_path, monkeypatch):
    store = tmp_path / "candidates.json"
    reset_identity_candidate_repository_for_tests(store)
    reset_identity_candidate_service_for_tests()

    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: _admin() if token == "admin" else None)

    svc = get_identity_candidate_service()
    row = svc.seed_demo_candidate({})
    cid = row["identity_candidate_id"]

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get(f"/api/identity/candidates/{cid}", headers={"Authorization": "Bearer admin"})
    assert res.status_code == 200
    body = res.json()
    assert body["item"]["explainability"]["wording"]["match_label"] == "Possible identity match"
