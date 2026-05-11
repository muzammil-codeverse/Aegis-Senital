from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import case_routes as case_routes_module
from app.api import object_authorization as authz_module
from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.services import evidence_file_service as evidence_file_service_module
from app.services.audit_log_service import AuditLogService
from app.services.case_service import CaseService
from app.services.evidence_file_service import EvidenceFileService
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


def _evidence_config(tmp_path):
    return {
        "evidence": {
            "enabled": True,
            "storage": {"local_dir": str(tmp_path / "evidence")},
            "hashing": {
                "required_for_file_backed_evidence": True,
                "algorithm": "sha256",
                "verify_on_download": True,
                "verify_on_export": True,
            },
            "access": {
                "require_case_access": True,
                "require_evidence_access": True,
                "sensitive_headers": True,
                "audit_downloads": True,
            },
            "uploads": {
                "enabled": True,
                "max_file_size_mb": 5,
                "allowed_extensions": {
                    "video": [".mp4", ".avi", ".mov", ".mkv"],
                    "image": [".jpg", ".jpeg", ".png"],
                    "document": [".pdf", ".txt", ".md", ".json", ".csv"],
                },
                "reject_archives": True,
                "reject_executables": True,
                "malware_scan_required_in_production": False,
                "malware_scan_placeholder": True,
            },
            "retention": {
                "enabled": True,
                "default_days": 180,
                "archived_case_days": 365,
                "legal_hold_blocks_deletion": True,
            },
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
        "admin": _user("admin"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
        "outsider": _user("viewer"),
    }
    auth_service = auth_module.get_auth_service()
    monkeypatch.setattr(auth_service, "get_current_user_from_token", lambda token: users.get(token))
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    evidence_service = EvidenceFileService(case_service=case_service, config=_evidence_config(tmp_path))
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
    monkeypatch.setattr(case_routes_module, "get_evidence_file_service", lambda: evidence_service)
    monkeypatch.setattr(case_routes_module, "get_audit_log_service", lambda: audit_service)
    monkeypatch.setattr(authz_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(evidence_file_service_module, "get_audit_log_service", lambda: audit_service)
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    return case_service, audit_service, users


def test_download_requires_case_access_and_wrong_user_is_denied(tmp_path, monkeypatch):
    case_service, _, users = _install(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "Protected evidence case"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    upload = client.post(
        f"/api/cases/{case.case_id}/evidence/upload",
        headers={"Authorization": "Bearer operator"},
        files={"file": ("note.txt", b"case evidence", "text/plain")},
        data={"title": "Protected note"},
    )
    assert upload.status_code == 200
    evidence_id = upload.json()["item"]["evidence_id"]

    denied = client.get(
        f"/api/cases/{case.case_id}/evidence/{evidence_id}/download",
        headers={"Authorization": "Bearer viewer"},
    )
    wrong_user = client.get(
        f"/api/cases/{case.case_id}/evidence/{evidence_id}/download",
        headers={"Authorization": "Bearer outsider"},
    )

    assert denied.status_code == 403
    assert wrong_user.status_code == 403


def test_download_has_sensitive_headers_and_upload_flow_works(tmp_path, monkeypatch):
    case_service, _, users = _install(tmp_path, monkeypatch)
    case = case_service.create_case({"title": "Download case"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    upload = client.post(
        f"/api/cases/{case.case_id}/evidence/upload",
        headers={"Authorization": "Bearer operator"},
        files={"file": ("note.txt", b"case evidence", "text/plain")},
        data={"title": "Protected note", "description": "Uploaded note"},
    )
    assert upload.status_code == 200
    evidence_id = upload.json()["item"]["evidence_id"]

    verify = client.post(
        f"/api/cases/{case.case_id}/evidence/{evidence_id}/verify",
        headers={"Authorization": "Bearer operator"},
    )
    assert verify.status_code == 200
    assert verify.json()["item"]["integrity_status"] == "verified"

    download = client.get(
        f"/api/cases/{case.case_id}/evidence/{evidence_id}/download",
        headers={"Authorization": "Bearer operator"},
    )
    assert download.status_code == 200
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "attachment;" in download.headers["content-disposition"]
