from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.case_models import CaseEvidence
from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.evidence_retention_service import EvidenceRetentionService


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


def _evidence_config():
    return {
        "evidence": {
            "retention": {
                "enabled": True,
                "default_days": 30,
                "archived_case_days": 60,
                "legal_hold_blocks_deletion": True,
            }
        }
    }


def test_legal_hold_blocks_retention_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    retention_service = EvidenceRetentionService(case_service=case_service, config=_evidence_config())
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()

    archived_case = case_service.create_case({"title": "Archived case"}, actor="operator")
    case_service.archive_case(archived_case.case_id, actor="operator", reason="archive")
    retained = case_service.store_evidence(
        CaseEvidence(
            case_id=archived_case.case_id,
            evidence_type="document",
            storage_uri="storage/evidence/archived/file.txt",
            created_at=old_timestamp,
            timestamp=old_timestamp,
            integrity_status="verified",
        ),
        actor="operator",
    )

    legal_hold_case = case_service.create_case({"title": "Legal hold case", "metadata": {"legal_hold": True}}, actor="operator")
    blocked = case_service.store_evidence(
        CaseEvidence(
            case_id=legal_hold_case.case_id,
            evidence_type="document",
            storage_uri="storage/evidence/legal_hold/file.txt",
            created_at=old_timestamp,
            timestamp=old_timestamp,
            integrity_status="verified",
            chain_status="legal_hold",
        ),
        actor="operator",
    )

    candidates = retention_service.dry_run()
    candidate_ids = {item["evidence_id"] for item in candidates}

    assert retained.evidence_id in candidate_ids
    assert blocked.evidence_id not in candidate_ids
