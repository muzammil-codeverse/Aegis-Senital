from fastapi.testclient import TestClient

from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.api import case_routes as case_routes_module
from app.services.case_service import CaseService
from main import app


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 10},
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


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))


def test_case_api_create_list_get_update_and_close(tmp_path, monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    monkeypatch.setattr(case_routes_module, "get_case_service", lambda: service)

    client = TestClient(app, raise_server_exceptions=False)
    create = client.post(
        "/api/cases",
        headers={"Authorization": "Bearer operator"},
        json={"title": "Possible restricted-zone incident", "severity": "high", "priority": "high"},
    )
    assert create.status_code == 200
    case_id = create.json()["item"]["case_id"]

    listing = client.get("/api/cases", headers={"Authorization": "Bearer viewer"})
    assert listing.status_code == 200
    assert listing.json()["count"] >= 1

    detail = client.get(f"/api/cases/{case_id}", headers={"Authorization": "Bearer viewer"})
    assert detail.status_code == 200

    update = client.patch(
        f"/api/cases/{case_id}",
        headers={"Authorization": "Bearer operator"},
        json={"status": "investigating"},
    )
    assert update.status_code == 200

    close = client.post(
        f"/api/cases/{case_id}/close",
        headers={"Authorization": "Bearer supervisor"},
        json={"reason": "Resolved by review"},
    )
    assert close.status_code == 200
    assert close.json()["item"]["status"] == "resolved"
