from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.case_models import CaseEvidence
from app.repositories.audit_repository import JsonlAuditLogRepository
from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.audit_log_service import AuditLogService
from app.services.case_service import CaseService
from app.services.evidence_retention_service import DELETE_CONFIRMATION_TOKEN, EvidenceRetentionService


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
            "storage": {
                "local_dir": str(tmp_path / "evidence"),
            },
            "retention": {
                "enabled": True,
                "default_mode": "dry_run",
                "default_days": 30,
                "archived_case_days": 60,
                "quarantine_dir": str(tmp_path / "evidence_quarantine"),
                "require_reviewed_mode": True,
                "delete_disabled_by_default": True,
                "delete_confirmation_token": DELETE_CONFIRMATION_TOKEN,
                "legal_hold_blocks_deletion": True,
            },
        }
    }


def _build_service(tmp_path):
    case_config = _case_config(tmp_path)
    case_service_module._CASE_SERVICE_SUBSCRIBED = True
    case_service = CaseService(repository=JsonlCaseRepository(config=case_config), config=case_config)
    audit = AuditLogService(
        config={"enabled": True, "hash_chain_enabled": True},
        repository=JsonlAuditLogRepository(config={"enabled": True, "storage_dir": str(tmp_path / "audit")}),
    )
    retention = EvidenceRetentionService(case_service=case_service, config=_evidence_config(tmp_path), audit_service=audit)
    return case_service, audit, retention


def _old_timestamp(days=120) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _store_old_file(case_service, case_id: str, file_path: Path, *, legal_hold: bool = False):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("retention-test", encoding="utf-8")
    return case_service.store_evidence(
        CaseEvidence(
            case_id=case_id,
            evidence_type="document",
            storage_uri=str(file_path),
            created_at=_old_timestamp(),
            timestamp=_old_timestamp(),
            integrity_status="verified",
            chain_status="legal_hold" if legal_hold else "active",
            metadata={"legal_hold": legal_hold},
        ),
        actor="operator",
    )


def test_retention_dry_run_deletes_nothing(tmp_path):
    case_service, _audit, retention = _build_service(tmp_path)
    case = case_service.create_case({"title": "Retention candidate"}, actor="operator")
    evidence_path = tmp_path / "evidence" / case.case_id / "candidate.txt"
    evidence = _store_old_file(case_service, case.case_id, evidence_path)

    candidates = retention.dry_run(case_id=case.case_id)

    assert len(candidates) == 1
    assert candidates[0]["evidence_id"] == evidence.evidence_id
    assert evidence_path.exists()


def test_quarantine_excludes_legal_hold(tmp_path):
    case_service, _audit, retention = _build_service(tmp_path)
    case = case_service.create_case({"title": "Held case", "metadata": {"legal_hold": True}}, actor="operator")
    held_path = tmp_path / "evidence" / case.case_id / "held.txt"
    _store_old_file(case_service, case.case_id, held_path, legal_hold=True)

    candidates = retention.dry_run(case_id=case.case_id)
    executed = retention.execute(mode="quarantine", case_id=case.case_id, require_review=True, requested_by="operator")

    assert candidates == []
    assert executed["executed_count"] == 0
    assert held_path.exists()


def test_quarantine_moves_eligible_file_and_updates_metadata(tmp_path):
    case_service, audit, retention = _build_service(tmp_path)
    case = case_service.create_case({"title": "Quarantine me"}, actor="operator")
    evidence_path = tmp_path / "evidence" / case.case_id / "candidate.txt"
    evidence = _store_old_file(case_service, case.case_id, evidence_path)

    result = retention.execute(
        mode="quarantine",
        case_id=case.case_id,
        require_review=True,
        reviewed_by="supervisor",
        requested_by="operator",
    )

    updated = case_service.get_evidence(evidence.evidence_id)
    assert result["executed_count"] == 1
    assert updated is not None
    assert updated.chain_status == "quarantined"
    assert updated.storage_uri is not None
    assert Path(updated.storage_uri).exists()
    assert not evidence_path.exists()
    assert any(entry["action"] == "evidence_retention_quarantine_started" for entry in audit.list_logs(limit=20))
    assert any(entry["action"] == "evidence_retention_quarantine_completed" for entry in audit.list_logs(limit=20))


def test_delete_requires_explicit_confirmation(tmp_path):
    case_service, _audit, retention = _build_service(tmp_path)
    case = case_service.create_case({"title": "Delete gated"}, actor="operator")
    evidence_path = tmp_path / "evidence" / case.case_id / "candidate.txt"
    _store_old_file(case_service, case.case_id, evidence_path)

    with pytest.raises(ValueError, match="explicit confirmation"):
        retention.execute(mode="delete", case_id=case.case_id, require_review=True)
