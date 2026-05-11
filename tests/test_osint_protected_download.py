from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import case_routes as case_routes_module
from app.api import object_authorization as authz_module
from app.api import osint_routes as osint_routes_module
from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.osint_repository import JsonlOsintRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.services import osint_file_service as osint_file_service_module
from app.services.audit_log_service import AuditLogService
from app.services.case_service import CaseService
from app.services.osint_file_service import OsintFileService
from app.services.osint_service import OsintEnrichmentService
from main import app


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 20},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _osint_config(tmp_path):
    return {
        "osint_enrichment": {
            "enabled": True,
            "mode": "analyst_provided_only",
            "storage": {"jsonl_dir": str(tmp_path / "osint")},
            "uploads": {
                "enabled": True,
                "storage_dir": str(tmp_path / "osint_uploads"),
                "max_file_size_mb": 5,
                "allowed_extensions": [".txt", ".pdf", ".png", ".jpg", ".jpeg", ".md", ".json", ".csv"],
            },
            "links": {
                "enabled": True,
                "require_manual_entry": True,
                "fetch_preview": False,
                "fetch_full_page": False,
            },
            "audit": {"log_all_enrichment_actions": True},
        }
    }


def _user(role: str, metadata: dict | None = None) -> UserAccount:
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


def _install(tmp_path, monkeypatch):
    users = {
        "operator": _user("operator"),
        "viewer": _user("viewer"),
        "outsider": _user("viewer"),
    }
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    osint_service = OsintEnrichmentService(repository=JsonlOsintRepository(config=_osint_config(tmp_path)), config=_osint_config(tmp_path))
    osint_file_service = OsintFileService(config=_osint_config(tmp_path))
    audit_service = AuditLogService(
        config={
            "enabled": True,
            "storage_dir": str(tmp_path / "audit"),
            "rotate_daily": False,
            "max_recent_entries": 200,
            "hash_chain_enabled": True,
        }
    )
    monkeypatch.setattr(case_routes_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(osint_routes_module, "get_osint_service", lambda: osint_service)
    monkeypatch.setattr(osint_routes_module, "get_osint_file_service", lambda: osint_file_service)
    monkeypatch.setattr(osint_routes_module, "get_audit_log_service", lambda: audit_service)
    monkeypatch.setattr(authz_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(authz_module, "get_osint_service", lambda: osint_service)
    monkeypatch.setattr(osint_file_service_module, "get_audit_log_service", lambda: audit_service)
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    return case_service, osint_service, users


def test_osint_download_requires_case_and_source_access(tmp_path, monkeypatch):
    case_service, _, users = _install(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "OSINT protected download"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    upload = client.post(
        f"/api/cases/{case.case_id}/enrichment/upload",
        headers={"Authorization": "Bearer operator"},
        files={"file": ("note.txt", b"manual osint content", "text/plain")},
        data={"title": "Manual upload"},
    )
    assert upload.status_code == 200
    source_id = upload.json()["item"]["source"]["source_id"]

    denied = client.get(
        f"/api/cases/{case.case_id}/enrichment/sources/{source_id}/download",
        headers={"Authorization": "Bearer viewer"},
    )
    assert denied.status_code == 403

    allowed = client.get(
        f"/api/cases/{case.case_id}/enrichment/sources/{source_id}/download",
        headers={"Authorization": "Bearer operator"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.headers["x-content-type-options"] == "nosniff"


def test_external_link_source_has_no_downloadable_artifact(tmp_path, monkeypatch):
    case_service, _, users = _install(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "OSINT external link"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    created = client.post(
        f"/api/cases/{case.case_id}/enrichment/links",
        headers={"Authorization": "Bearer operator"},
        json={
            "source_type": "external_link",
            "title": "Manual source",
            "url": "https://example.com/report",
            "description": "Analyst-provided context",
            "source_reliability": "medium",
            "metadata": {},
        },
    )
    assert created.status_code == 200
    source_id = created.json()["item"]["source_id"]

    response = client.get(
        f"/api/cases/{case.case_id}/enrichment/sources/{source_id}/download",
        headers={"Authorization": "Bearer operator"},
    )
    assert response.status_code == 400
    assert "no local file artifact exists" in response.json()["detail"].lower()
