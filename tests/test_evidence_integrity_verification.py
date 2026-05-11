from __future__ import annotations

from io import BytesIO
from pathlib import Path

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


def test_hash_mismatch_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    evidence_service = EvidenceFileService(case_service=case_service, config=_evidence_config(tmp_path))
    case = case_service.create_case({"title": "Hash mismatch case"}, actor="operator")

    evidence = evidence_service.upload_case_evidence_file(case.case_id, _Upload("note.txt", b"original", "text/plain"), {"title": "note"}, _user())
    target = Path(str(evidence.storage_uri))
    if not target.is_absolute():
        target = Path.cwd() / target
    target.write_text("tampered", encoding="utf-8")

    result = evidence_service.verify_case_evidence_file(case.case_id, evidence.evidence_id, _user())
    assert result.integrity_status == "hash_mismatch"


def test_missing_file_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    evidence_service = EvidenceFileService(case_service=case_service, config=_evidence_config(tmp_path))
    case = case_service.create_case({"title": "Missing evidence case"}, actor="operator")

    evidence = evidence_service.upload_case_evidence_file(case.case_id, _Upload("note.txt", b"original", "text/plain"), {"title": "note"}, _user())
    target = Path(str(evidence.storage_uri))
    if not target.is_absolute():
        target = Path.cwd() / target
    target.unlink()

    result = evidence_service.verify_case_evidence_file(case.case_id, evidence.evidence_id, _user())
    assert result.integrity_status == "missing_file"
