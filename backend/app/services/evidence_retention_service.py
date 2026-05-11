from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.case_service import CaseService, get_case_service
from app.services.evidence_integrity import get_evidence_runtime_settings, safe_evidence_metadata


class EvidenceRetentionService:
    def __init__(self, case_service: CaseService | None = None, config: dict[str, Any] | None = None) -> None:
        self._case_service = case_service or get_case_service()
        self._raw_config = config or {"evidence": get_evidence_runtime_settings()}
        self._config = dict((self._raw_config.get("evidence") or {}).get("retention") or {})

    def dry_run(self, *, case_id: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
        if not bool(self._config.get("enabled", True)):
            return []
        current = now or datetime.now(timezone.utc)
        cases = [self._case_service.get_case(case_id)] if case_id else self._case_service.list_cases({"limit": 5000})
        candidates: list[dict[str, Any]] = []
        for case in cases:
            if case is None:
                continue
            case_legal_hold = bool((case.metadata or {}).get("legal_hold", False))
            retention_days = int(self._config.get("archived_case_days") or 365) if str(case.status).lower() == "archived" else int(self._config.get("default_days") or 180)
            for evidence in self._case_service.list_evidence(case.case_id):
                if not evidence.storage_uri or evidence.chain_status == "deleted":
                    continue
                evidence_legal_hold = case_legal_hold or evidence.chain_status == "legal_hold" or bool((evidence.metadata or {}).get("legal_hold", False))
                if evidence_legal_hold and bool(self._config.get("legal_hold_blocks_deletion", True)):
                    continue
                age_days = self._age_days(evidence.created_at, current)
                if age_days < retention_days:
                    continue
                candidates.append(
                    safe_evidence_metadata(
                        {
                            "case_id": case.case_id,
                            "evidence_id": evidence.evidence_id,
                            "storage_uri": evidence.storage_uri,
                            "created_at": evidence.created_at,
                            "age_days": age_days,
                            "retention_days": retention_days,
                            "case_status": case.status,
                            "chain_status": evidence.chain_status,
                            "legal_hold": evidence_legal_hold,
                        }
                    )
                )
        candidates.sort(key=lambda item: (str(item.get("case_id") or ""), str(item.get("evidence_id") or "")))
        return candidates

    @staticmethod
    def _age_days(created_at: str | None, current: datetime) -> int:
        if not created_at:
            return 0
        try:
            started = datetime.fromisoformat(created_at)
        except ValueError:
            return 0
        return max(0, int((current - started.astimezone(timezone.utc)).days))


_EVIDENCE_RETENTION_SERVICE: EvidenceRetentionService | None = None


def get_evidence_retention_service() -> EvidenceRetentionService:
    global _EVIDENCE_RETENTION_SERVICE
    if _EVIDENCE_RETENTION_SERVICE is None:
        _EVIDENCE_RETENTION_SERVICE = EvidenceRetentionService()
    return _EVIDENCE_RETENTION_SERVICE
