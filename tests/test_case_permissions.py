from fastapi.testclient import TestClient

from app.api import case_routes as case_routes_module
from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from main import app


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


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


def test_case_permissions_enforced(tmp_path, monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    monkeypatch.setattr(case_routes_module, "get_case_service", lambda: service)

    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/api/cases",
        headers={"Authorization": "Bearer operator"},
        json={"title": "Possible incident", "severity": "high", "priority": "high"},
    )
    case_id = created.json()["item"]["case_id"]

    assert client.get("/api/cases", headers={"Authorization": "Bearer viewer"}).status_code == 200
    assert client.post("/api/cases", headers={"Authorization": "Bearer viewer"}, json={"title": "Denied"}).status_code == 403
    assert client.post(f"/api/cases/{case_id}/assign", headers={"Authorization": "Bearer operator"}, json={"assigned_to": "alice"}).status_code == 200
    assert client.post(f"/api/cases/{case_id}/close", headers={"Authorization": "Bearer operator"}, json={"reason": "Denied"}).status_code == 403
    assert client.get(f"/api/cases/{case_id}/export", headers={"Authorization": "Bearer supervisor"}).status_code == 200
