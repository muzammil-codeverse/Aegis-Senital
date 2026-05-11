from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.case_models import CaseEvidence, CaseRecord
from app.repositories.retention_repository import (
    RetentionActionRepository,
    build_retention_action_repository,
)
from app.services.audit_log_service import AuditLogService, get_audit_log_service
from app.services.case_service import CaseService, get_case_service
from app.services.evidence_integrity import (
    PROJECT_ROOT as EVIDENCE_PROJECT_ROOT,
    ensure_managed_path,
    get_evidence_runtime_settings,
    get_evidence_storage_root,
    resolve_local_storage_uri,
    safe_evidence_metadata,
)


DELETE_CONFIRMATION_TOKEN = "DELETE_EXPIRED_EVIDENCE"


class EvidenceRetentionService:
    def __init__(
        self,
        case_service: CaseService | None = None,
        config: dict[str, Any] | None = None,
        *,
        audit_service: AuditLogService | None = None,
        repository: RetentionActionRepository | None = None,
    ) -> None:
        self._case_service = case_service or get_case_service()
        self._raw_config = config or {"evidence": get_evidence_runtime_settings()}
        self._settings = dict(self._raw_config.get("evidence") or get_evidence_runtime_settings())
        self._config = dict(self._settings.get("retention") or {})
        self._audit = audit_service or get_audit_log_service()
        self._storage_root = get_evidence_storage_root(self._raw_config)
        quarantine_dir = str(self._config.get("quarantine_dir") or "storage/evidence_quarantine")
        candidate_dir = Path(quarantine_dir)
        if not candidate_dir.is_absolute():
            candidate_dir = (EVIDENCE_PROJECT_ROOT / candidate_dir).resolve()
        self._quarantine_dir = candidate_dir
        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._repository = repository or build_retention_action_repository(str(self._quarantine_dir.parent))

    def dry_run(self, *, case_id: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
        return [
            candidate
            for _, _, candidate in self._collect_candidates(
                case_id=case_id,
                now=now or datetime.now(timezone.utc),
                mode=None,
            )
        ]

    def execute(
        self,
        *,
        mode: str,
        case_id: str | None = None,
        now: datetime | None = None,
        require_review: bool = False,
        reviewed_by: str = "reviewed",
        requested_by: str = "system",
        confirm_delete: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode not in {"quarantine", "delete"}:
            raise ValueError("Retention execution mode must be 'quarantine' or 'delete'")
        if bool(self._config.get("require_reviewed_mode", True)) and not require_review:
            raise ValueError("Retention execution requires explicit reviewed mode")
        if normalized_mode == "delete":
            confirmation_token = str(self._config.get("delete_confirmation_token") or DELETE_CONFIRMATION_TOKEN)
            if confirm_delete != confirmation_token:
                raise ValueError("Delete mode requires explicit confirmation")

        current = now or datetime.now(timezone.utc)
        actions: list[dict[str, Any]] = []
        for case, evidence, candidate in self._collect_candidates(
            case_id=case_id,
            now=current,
            mode=normalized_mode,
        ):
            action = self._execute_candidate(
                case,
                evidence,
                candidate,
                mode=normalized_mode,
                reviewed_by=reviewed_by,
                requested_by=requested_by,
                now=current,
            )
            actions.append(action)
        return {
            "mode": normalized_mode,
            "case_id": case_id,
            "executed_count": len(actions),
            "actions": actions,
        }

    def current_mode(self) -> str:
        return str(self._config.get("default_mode") or "dry_run")

    def health_check(self) -> dict[str, Any]:
        payload = self._repository.health_check().to_dict()
        payload["retention_mode"] = self.current_mode()
        payload["quarantine_dir"] = str(self._quarantine_dir)
        payload["require_reviewed_mode"] = bool(self._config.get("require_reviewed_mode", True))
        payload["delete_disabled_by_default"] = bool(self._config.get("delete_disabled_by_default", True))
        payload["last_backup_at"] = None
        return payload

    def list_actions(
        self,
        *,
        case_id: str | None = None,
        evidence_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return self._repository.list_actions(case_id=case_id, evidence_id=evidence_id, limit=limit)

    def _collect_candidates(
        self,
        *,
        case_id: str | None,
        now: datetime,
        mode: str | None,
    ) -> list[tuple[CaseRecord, CaseEvidence, dict[str, Any]]]:
        if not bool(self._config.get("enabled", True)):
            return []
        cases = [self._case_service.get_case(case_id)] if case_id else self._case_service.list_cases({"limit": 5000})
        candidates: list[tuple[CaseRecord, CaseEvidence, dict[str, Any]]] = []
        for case in cases:
            if case is None:
                continue
            case_legal_hold = bool((case.metadata or {}).get("legal_hold", False))
            retention_days = int(self._config.get("archived_case_days") or 365) if str(case.status).lower() == "archived" else int(self._config.get("default_days") or 180)
            for evidence in self._case_service.list_evidence(case.case_id):
                if not evidence.storage_uri or evidence.chain_status == "deleted":
                    continue
                if mode == "quarantine" and evidence.chain_status == "quarantined":
                    continue
                evidence_legal_hold = case_legal_hold or evidence.chain_status == "legal_hold" or bool((evidence.metadata or {}).get("legal_hold", False))
                if evidence_legal_hold and bool(self._config.get("legal_hold_blocks_deletion", True)):
                    continue
                age_days = self._age_days(evidence.created_at, now)
                if age_days < retention_days:
                    continue
                candidate = safe_evidence_metadata(
                    {
                        "case_id": case.case_id,
                        "evidence_id": evidence.evidence_id,
                        "storage_uri": evidence.storage_uri,
                        "created_at": evidence.created_at,
                        "age_days": age_days,
                        "retention_days": retention_days,
                        "case_status": case.status,
                        "chain_status": evidence.chain_status,
                        "retention_mode": mode or self.current_mode(),
                        "legal_hold": evidence_legal_hold,
                        "hash_sha256": evidence.hash_sha256,
                    }
                )
                candidates.append((case, evidence, candidate))
        candidates.sort(key=lambda item: (str(item[2].get("case_id") or ""), str(item[2].get("evidence_id") or "")))
        return candidates

    def _execute_candidate(
        self,
        case: CaseRecord,
        evidence: CaseEvidence,
        candidate: dict[str, Any],
        *,
        mode: str,
        reviewed_by: str,
        requested_by: str,
        now: datetime,
    ) -> dict[str, Any]:
        action_id = f"retain_{uuid.uuid4().hex[:16]}"
        action_record = {
            "action_id": action_id,
            "case_id": case.case_id,
            "evidence_id": evidence.evidence_id,
            "mode": mode,
            "status": "started",
            "requested_by": requested_by,
            "reviewed_by": reviewed_by,
            "review_required": bool(self._config.get("review_required", True)),
            "storage_uri": evidence.storage_uri,
            "hash_sha256": evidence.hash_sha256,
            "before_metadata": candidate,
            "after_metadata": {},
            "metadata": {"case_status": case.status},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "action_completed_at": None,
        }
        self._repository.append_action(action_record)
        self._audit.record(
            f"evidence_retention_{mode}_started",
            resource_type="evidence",
            resource_id=evidence.evidence_id,
            metadata={"case_id": case.case_id, "action_id": action_id, "mode": mode},
        )
        try:
            if mode == "quarantine":
                result = self._quarantine_evidence(case, evidence, action_id=action_id, actor=requested_by, now=now)
            else:
                result = self._delete_evidence(case, evidence, action_id=action_id, actor=requested_by, now=now)
        except Exception as exc:
            failed_at = datetime.now(timezone.utc).isoformat()
            failed_record = {
                **action_record,
                "status": "failed",
                "metadata": safe_evidence_metadata(
                    {
                        **(action_record.get("metadata") or {}),
                        "error": str(exc),
                    }
                ),
                "updated_at": failed_at,
                "action_completed_at": failed_at,
            }
            self._repository.append_action(failed_record)
            self._audit.record(
                f"evidence_retention_{mode}_failed",
                resource_type="evidence",
                resource_id=evidence.evidence_id,
                metadata={"case_id": case.case_id, "action_id": action_id, "mode": mode, "error": str(exc)},
            )
            raise

        completed_at = datetime.now(timezone.utc).isoformat()
        final_record = {
            **action_record,
            "status": result["status"],
            "after_metadata": safe_evidence_metadata(result),
            "updated_at": completed_at,
            "action_completed_at": completed_at,
        }
        self._repository.append_action(final_record)
        self._audit.record(
            f"evidence_retention_{mode}_completed",
            resource_type="evidence",
            resource_id=evidence.evidence_id,
            metadata={"case_id": case.case_id, "action_id": action_id, "mode": mode, "status": result["status"]},
        )
        return final_record

    def _quarantine_evidence(
        self,
        case: CaseRecord,
        evidence: CaseEvidence,
        *,
        action_id: str,
        actor: str,
        now: datetime,
    ) -> dict[str, Any]:
        source_path = self._resolve_managed_local_path(evidence.storage_uri)
        if source_path is None or not source_path.exists():
            raise FileNotFoundError(f"Evidence file is unavailable for quarantine: {evidence.storage_uri}")
        if self._quarantine_dir in source_path.parents:
            updated = self._case_service.update_evidence(
                evidence.evidence_id,
                {
                    "chain_status": "quarantined",
                    "metadata": safe_evidence_metadata(
                        {
                            **(evidence.metadata or {}),
                            "retention_action_id": action_id,
                            "retention_quarantined_at": now.isoformat(),
                            "retention_original_storage_uri": (evidence.metadata or {}).get("retention_original_storage_uri") or evidence.storage_uri,
                        }
                    ),
                },
                actor=actor,
            )
            return {
                "status": "quarantined",
                "case_id": case.case_id,
                "evidence_id": updated.evidence_id,
                "storage_uri": updated.storage_uri,
                "hash_sha256": updated.hash_sha256,
                "chain_status": updated.chain_status,
            }
        relative_name = source_path.name
        target_dir = self._quarantine_dir / case.case_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = (target_dir / relative_name).resolve()
        shutil.move(str(source_path), str(target_path))
        updated = self._case_service.update_evidence(
            evidence.evidence_id,
            {
                "storage_uri": str(target_path),
                "chain_status": "quarantined",
                "metadata": safe_evidence_metadata(
                    {
                        **(evidence.metadata or {}),
                        "retention_action_id": action_id,
                        "retention_quarantined_at": now.isoformat(),
                        "retention_original_storage_uri": evidence.storage_uri,
                    }
                ),
            },
            actor=actor,
        )
        return {
            "status": "quarantined",
            "case_id": case.case_id,
            "evidence_id": updated.evidence_id,
            "storage_uri": updated.storage_uri,
            "hash_sha256": updated.hash_sha256,
            "chain_status": updated.chain_status,
        }

    def _delete_evidence(
        self,
        case: CaseRecord,
        evidence: CaseEvidence,
        *,
        action_id: str,
        actor: str,
        now: datetime,
    ) -> dict[str, Any]:
        source_path = self._resolve_managed_local_path(evidence.storage_uri)
        if source_path is not None and source_path.exists():
            source_path.unlink()
        updated = self._case_service.update_evidence(
            evidence.evidence_id,
            {
                "storage_uri": None,
                "chain_status": "deleted",
                "metadata": safe_evidence_metadata(
                    {
                        **(evidence.metadata or {}),
                        "retention_action_id": action_id,
                        "retention_deleted_at": now.isoformat(),
                        "retention_deleted_storage_uri": evidence.storage_uri,
                    }
                ),
            },
            actor=actor,
        )
        return {
            "status": "deleted",
            "case_id": case.case_id,
            "evidence_id": updated.evidence_id,
            "storage_uri": updated.storage_uri,
            "hash_sha256": updated.hash_sha256,
            "chain_status": updated.chain_status,
        }

    def _resolve_managed_local_path(self, storage_uri: str | None) -> Path | None:
        resolved = resolve_local_storage_uri(storage_uri)
        if resolved is None:
            return None
        return ensure_managed_path(str(resolved), [self._storage_root, self._quarantine_dir])

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


def reset_evidence_retention_service() -> None:
    global _EVIDENCE_RETENTION_SERVICE
    _EVIDENCE_RETENTION_SERVICE = None
