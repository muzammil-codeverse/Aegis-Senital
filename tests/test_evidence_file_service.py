from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException

from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.evidence_file_service import EvidenceFileService


class _Upload:
    def __init__(self, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


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
                "max_file_size_mb": 1,
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


def _user() -> UserAccount:
    return UserAccount(
        user_id="user-operator",
        username="operator",
        display_name="Operator",
        role="operator",
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata={},
    )


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    return case_service, EvidenceFileService(case_service=case_service, config=_evidence_config(tmp_path))


def test_valid_case_evidence_upload_accepted(service):
    case_service, evidence_service = service
    case = case_service.create_case({"title": "Upload case"}, actor="operator")

    evidence = evidence_service.upload_case_evidence_file(
        case.case_id,
        _Upload("notes.txt", b"operator evidence", "text/plain"),
        {"title": "Operator upload"},
        _user(),
    )

    assert evidence.case_id == case.case_id
    assert evidence.integrity_status == "verified"
    assert evidence.hash_sha256
    assert evidence.safe_filename.endswith(".txt")
    assert ".." not in evidence.storage_uri


def test_executable_upload_rejected(service):
    case_service, evidence_service = service
    case = case_service.create_case({"title": "Executable case"}, actor="operator")

    with pytest.raises(HTTPException, match="Rejected file type"):
        evidence_service.upload_case_evidence_file(
            case.case_id,
            _Upload("payload.exe", b"MZfake", "application/octet-stream"),
            {"title": "Blocked"},
            _user(),
        )


def test_path_traversal_filename_rejected(service):
    case_service, evidence_service = service
    case = case_service.create_case({"title": "Traversal case"}, actor="operator")

    with pytest.raises(HTTPException, match="Unsafe filename"):
        evidence_service.upload_case_evidence_file(
            case.case_id,
            _Upload("..\\secret.txt", b"nope", "text/plain"),
            {"title": "Blocked"},
            _user(),
        )


def test_oversized_file_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    evidence_cfg = _evidence_config(tmp_path)
    evidence_cfg["evidence"]["uploads"]["max_file_size_mb"] = 1
    evidence_service = EvidenceFileService(case_service=case_service, config=evidence_cfg)
    case = case_service.create_case({"title": "Oversize case"}, actor="operator")

    with pytest.raises(HTTPException, match="maximum size"):
        evidence_service.upload_case_evidence_file(
            case.case_id,
            _Upload("huge.txt", b"x" * (2 * 1024 * 1024), "text/plain"),
            {"title": "Blocked"},
            _user(),
        )
