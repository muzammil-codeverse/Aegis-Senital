from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

from app.models.case_models import EvidenceManifest, EvidenceManifestItem
from app.repositories.case_repository import CaseRepository
from app.services.evidence_integrity import safe_evidence_metadata

if TYPE_CHECKING:
    from app.services.case_service import CaseService


class ChainOfCustodyService:
    def __init__(self, case_service: "CaseService | None" = None, repository: CaseRepository | None = None) -> None:
        self._case_service = case_service
        if self._case_service is None and repository is None:
            from app.services.case_service import get_case_service

            self._case_service = get_case_service()
        self._repository = repository or getattr(self._case_service, "repository", None)

    def build_manifest(self, case_id: str, generated_by: str = "system") -> EvidenceManifest:
        case = self._case_service.get_case(case_id) if self._case_service is not None else None
        if case is None and self._repository is not None:
            case = self._repository.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        if self._case_service is not None:
            evidence = self._case_service.list_evidence(case_id)
        elif self._repository is not None:
            evidence = self._repository.list_evidence(case_id)
        else:
            evidence = []
        audits = self._repository.list_audit_logs(case_id) if self._repository is not None else []
        counts = {
            "uploads": 0,
            "downloads": 0,
            "verifications": 0,
            "exports": 0,
        }
        for item in audits:
            action = str(item.action or "").lower()
            if action == "case_evidence_file_uploaded":
                counts["uploads"] += 1
            elif action == "case_evidence_file_downloaded":
                counts["downloads"] += 1
            elif action == "case_evidence_file_verified":
                counts["verifications"] += 1
            elif action in {"case_exported", "case_evidence_manifest_exported"}:
                counts["exports"] += 1

        items = [
            EvidenceManifestItem(
                evidence_id=item.evidence_id,
                type=item.evidence_type,
                filename=item.safe_filename or item.original_filename,
                hash_sha256=item.hash_sha256,
                size_bytes=item.size_bytes,
                integrity_status=item.integrity_status,
                created_at=item.created_at,
            )
            for item in evidence
            if item.storage_uri or item.hash_sha256 or item.integrity_status != "not_applicable"
        ]
        metadata: dict[str, Any] = {
            "case_status": case.status,
            "case_priority": case.priority,
            "case_severity": case.severity,
            "legal_hold": bool((case.metadata or {}).get("legal_hold", False)),
            "case_metadata": safe_evidence_metadata(case.metadata),
        }
        return EvidenceManifest(
            case_id=case_id,
            generated_by=generated_by,
            evidence_items=items,
            audit_summary=counts,
            metadata=metadata,
        )


_CHAIN_OF_CUSTODY_SERVICE: ChainOfCustodyService | None = None


def get_chain_of_custody_service() -> ChainOfCustodyService:
    global _CHAIN_OF_CUSTODY_SERVICE
    if _CHAIN_OF_CUSTODY_SERVICE is None:
        _CHAIN_OF_CUSTODY_SERVICE = ChainOfCustodyService()
    return _CHAIN_OF_CUSTODY_SERVICE
