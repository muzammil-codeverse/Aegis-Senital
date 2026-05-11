from __future__ import annotations

from io import BytesIO

from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.chain_of_custody_service import ChainOfCustodyService
from app.services.evidence_file_service import EvidenceFileService
from app.models.security_models import UserAccount


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


def test_manifest_includes_all_file_backed_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    evidence_service = EvidenceFileService(case_service=case_service, config=_evidence_config(tmp_path))
    chain_service = ChainOfCustodyService(case_service=case_service)
    case = case_service.create_case({"title": "Manifest case"}, actor="operator")

    first = evidence_service.upload_case_evidence_file(case.case_id, _Upload("one.txt", b"one", "text/plain"), {"title": "one"}, _user())
    second = evidence_service.upload_case_evidence_file(case.case_id, _Upload("two.txt", b"two", "text/plain"), {"title": "two"}, _user())
    case_service.add_evidence(case.case_id, {"evidence_type": "event", "title": "metadata only"}, actor="operator")

    manifest = chain_service.build_manifest(case.case_id, generated_by="operator")
    evidence_ids = {item.evidence_id for item in manifest.evidence_items}

    assert first.evidence_id in evidence_ids
    assert second.evidence_id in evidence_ids
    assert len(manifest.evidence_items) == 2

    export = case_service.export_case(case.case_id, format="json", actor="operator")
    assert "chain_of_custody_manifest" in export.content
