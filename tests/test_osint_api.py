from fastapi.testclient import TestClient

from app.api import case_routes as case_routes_module
from app.api import object_authorization as authz_module
from app.api import osint_routes as osint_routes_module
from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.osint_repository import JsonlOsintRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.services.audit_log_service import AuditLogService
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from app.services.osint_service import OsintEnrichmentService
from app.services.osint_summary_service import OsintSummaryService
from main import app


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 10},
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
                "storage_dir": str(tmp_path / "uploads"),
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
            "llm": {
                "summarize_uploaded_text": True,
                "summarize_external_link_metadata": True,
                "require_source_grounding": True,
                "require_operator_review_caveat": True,
            },
        }
    }


def _llm_config():
    return {
        "llm": {
            "enabled": True,
            "provider": "local_stub",
            "default_provider": "local_stub",
            "providers": {
                "local_stub": {"enabled": True},
                "openai": {"enabled": False},
            },
            "safety": {
                "max_input_events": 100,
                "max_input_evidence_items": 100,
                "max_notes": 50,
            },
            "reports": {"save_generated_reports": False},
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


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def _install_services(tmp_path, monkeypatch):
    users = _install_auth(monkeypatch)
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    osint_service = OsintEnrichmentService(
        repository=JsonlOsintRepository(config=_osint_config(tmp_path)),
        config=_osint_config(tmp_path),
        summary_service=OsintSummaryService(config=_osint_config(tmp_path)),
    )
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
    monkeypatch.setattr(osint_routes_module, "get_audit_log_service", lambda: audit_service)
    monkeypatch.setattr(authz_module, "get_osint_service", lambda: osint_service)
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    monkeypatch.setattr("app.services.osint_summary_service.get_llm_service", lambda: llm_service)
    monkeypatch.setattr("app.services.osint_service.get_case_service", lambda: case_service, raising=False)
    return case_service, osint_service, audit_service, users


def test_osint_api_create_list_update_delete_and_summarize(tmp_path, monkeypatch):
    case_service, osint_service, audit_service, users = _install_services(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "Possible analyst review case"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    users["viewer"].metadata = {"case_scopes": [case.case_id]}
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

    listing = client.get(
        f"/api/cases/{case.case_id}/enrichment/sources",
        headers={"Authorization": "Bearer viewer"},
    )
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    updated = client.patch(
        f"/api/cases/{case.case_id}/enrichment/sources/{source_id}",
        headers={"Authorization": "Bearer operator"},
        json={"source_reliability": "high"},
    )
    assert updated.status_code == 200
    assert updated.json()["item"]["source_reliability"] == "high"

    summarized = client.post(
        f"/api/cases/{case.case_id}/enrichment/summarize",
        headers={"Authorization": "Bearer operator"},
        json={"source_ids": [source_id]},
    )
    assert summarized.status_code == 200
    assert summarized.json()["item"]["source_references"]
    assert "analyst-provided material" in summarized.json()["item"]["operator_review_caveat"].lower()

    deleted = client.delete(
        f"/api/cases/{case.case_id}/enrichment/sources/{source_id}",
        headers={"Authorization": "Bearer operator"},
    )
    assert deleted.status_code == 200
    assert osint_service.list_audit_logs(case.case_id)
    assert any(entry["action"].startswith("osint_") for entry in audit_service.get_recent(limit=20))


def test_osint_api_upload_and_rbac(tmp_path, monkeypatch):
    case_service, _, _, users = _install_services(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "Possible upload review case"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    users["viewer"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    denied = client.post(
        f"/api/cases/{case.case_id}/enrichment/upload",
        headers={"Authorization": "Bearer viewer"},
        files={"file": ("note.txt", b"manual content", "text/plain")},
        data={"title": "Manual upload"},
    )
    assert denied.status_code == 403

    uploaded = client.post(
        f"/api/cases/{case.case_id}/enrichment/upload",
        headers={"Authorization": "Bearer operator"},
        files={"file": ("note.txt", b"manual content", "text/plain")},
        data={"title": "Manual upload", "description": "Uploaded by analyst", "source_reliability": "medium"},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["item"]["source"]["source_type"] == "uploaded_document"
