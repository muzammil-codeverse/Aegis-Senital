from __future__ import annotations

from typing import Any

from app.models.osint_models import (
    CaseDocumentSummary,
    CaseEnrichmentAuditLog,
    CaseExternalSource,
    CaseExternalSourceCreateRequest,
)
from app.repositories.osint_repository import OsintRepository, get_osint_repository, load_osint_config
from app.services.evidence_integrity import safe_evidence_metadata
from app.services.osint_file_service import OsintFileService
from app.services.osint_link_service import OsintLinkService
from app.services.osint_summary_service import OsintSummaryService


class OsintEnrichmentService:
    def __init__(
        self,
        repository: OsintRepository | None = None,
        config: dict[str, Any] | None = None,
        file_service: OsintFileService | None = None,
        link_service: OsintLinkService | None = None,
        summary_service: OsintSummaryService | None = None,
    ) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict(self._raw_config.get("osint_enrichment") or {})
        self._repository = repository or get_osint_repository()
        self._file_service = file_service or OsintFileService(self._raw_config)
        self._link_service = link_service or OsintLinkService(self._raw_config)
        self._summary_service = summary_service or OsintSummaryService(self._raw_config)

    @property
    def repository(self) -> OsintRepository:
        return self._repository

    def health(self) -> dict[str, Any]:
        return self._repository.health()

    def create_source(self, case_id: str, payload: CaseExternalSourceCreateRequest | dict[str, Any], actor: str = "system") -> CaseExternalSource:
        self._ensure_case_exists(case_id)
        request = payload if isinstance(payload, CaseExternalSourceCreateRequest) else CaseExternalSourceCreateRequest.model_validate(payload)
        if request.source_type == "external_link":
            if not request.url:
                raise ValueError("url is required for external_link sources")
            source = self._link_service.create_source(
                case_id=case_id,
                title=request.title,
                url=request.url,
                description=request.description,
                source_reliability=request.source_reliability,
                actor=actor,
                metadata=request.metadata,
            )
        else:
            source = CaseExternalSource(
                case_id=case_id,
                source_type=request.source_type,
                title=request.title,
                description=request.description,
                url=request.url,
                source_reliability=request.source_reliability,
                analyst_provided=True,
                created_by=actor,
                metadata=request.metadata,
                requires_review=True,
            )
        stored = self._repository.create_source(source)
        self._audit(case_id, stored.source_id, "osint_source_created", actor, {"source_type": stored.source_type})
        self._increment_metric("osint_sources_created_total")
        if stored.source_type == "external_link":
            self._increment_metric("osint_links_added_total")
        return stored

    def create_uploaded_source(
        self,
        *,
        case_id: str,
        filename: str,
        content: bytes,
        content_type: str | None,
        title: str,
        description: str,
        source_reliability: str,
        metadata: dict[str, Any] | None,
        actor: str = "system",
    ) -> tuple[CaseExternalSource, dict[str, Any]]:
        self._ensure_case_exists(case_id)
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        source_type = "uploaded_image" if f".{ext}" in {".png", ".jpg", ".jpeg"} else "uploaded_document"
        source = CaseExternalSource(
            case_id=case_id,
            source_type=source_type,
            title=title,
            description=description,
            source_reliability=source_reliability,
            analyst_provided=True,
            created_by=actor,
            metadata=dict(metadata or {}),
            requires_review=True,
        )
        stored = self._repository.create_source(source)
        upload = self._file_service.save_upload(
            case_id=case_id,
            source_id=stored.source_id,
            filename=filename,
            content=content,
            content_type=content_type,
            actor=actor,
            metadata=metadata,
        )
        stored = self._repository.update_source(
            stored.source_id,
            {
                "storage_uri": upload.storage_uri,
                "metadata": {
                    **stored.metadata,
                    "filename": upload.filename,
                    "content_type": upload.content_type,
                    "extension": upload.extension,
                    "size_bytes": upload.size_bytes,
                    "sha256": upload.sha256,
                },
            },
        )
        self._audit(case_id, stored.source_id, "osint_document_uploaded", actor, {"source_type": stored.source_type})
        self._increment_metric("osint_sources_created_total")
        self._increment_metric("osint_documents_uploaded_total")
        return stored, upload.model_dump(mode="json")

    def get_source(self, source_id: str) -> CaseExternalSource | None:
        return self._repository.get_source(source_id)

    def list_sources(self, case_id: str) -> list[CaseExternalSource]:
        return self._repository.list_sources(case_id)

    def update_source(self, source_id: str, updates: dict[str, Any], actor: str = "system") -> CaseExternalSource:
        source = self._repository.update_source(source_id, updates)
        self._audit(source.case_id, source.source_id, "osint_source_updated", actor, {"updated_fields": sorted(updates.keys())})
        return source

    def delete_source(self, source_id: str, actor: str = "system") -> bool:
        source = self._repository.get_source(source_id)
        if source is None:
            return False
        deleted = self._repository.delete_source(source_id)
        if deleted:
            self._audit(source.case_id, source_id, "osint_source_deleted", actor, {})
        return deleted

    def summarize(self, case_id: str, source_ids: list[str] | None = None, actor: str = "system", operator_instructions: str = "", escalate: bool = False) -> CaseDocumentSummary:
        available = self._repository.list_sources(case_id)
        if source_ids:
            requested = set(source_ids)
            available = [item for item in available if item.source_id in requested]
        summary = self._summary_service.summarize_sources(
            case_id=case_id,
            sources=available,
            actor=actor,
            operator_instructions=operator_instructions,
            escalate=escalate,
        )
        stored = self._repository.save_summary(summary)
        for source_id in summary.source_ids:
            try:
                self._repository.update_source(source_id, {"summary": summary.summary})
            except Exception:
                continue
        self._audit(case_id, None, "osint_summary_generated", actor, {"source_count": len(summary.source_ids)})
        self._increment_metric("osint_summaries_generated_total")
        return stored

    def list_summaries(self, case_id: str) -> list[CaseDocumentSummary]:
        return self._repository.list_summaries(case_id)

    def list_audit_logs(self, case_id: str) -> list[CaseEnrichmentAuditLog]:
        return self._repository.list_audit_logs(case_id)

    def _audit(self, case_id: str, source_id: str | None, action: str, actor: str, metadata: dict[str, Any]) -> None:
        if not bool((self._config.get("audit") or {}).get("log_all_enrichment_actions", True)):
            return
        self._repository.add_audit_log(
            CaseEnrichmentAuditLog(
                case_id=case_id,
                source_id=source_id,
                action=action,
                actor=actor,
                detail=action.replace("_", " "),
                metadata=safe_evidence_metadata(metadata),
            )
        )

    @staticmethod
    def _ensure_case_exists(case_id: str) -> None:
        from app.services.case_service import get_case_service

        if get_case_service().get_case(case_id) is None:
            raise KeyError(case_id)

    @staticmethod
    def _increment_metric(name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics

            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics as system_metrics

            system_metrics.increment(name, count)
        except Exception:
            pass


_OSINT_SERVICE: "OsintEnrichmentService | None" = None


def get_osint_service() -> OsintEnrichmentService:
    global _OSINT_SERVICE
    if _OSINT_SERVICE is None:
        _OSINT_SERVICE = OsintEnrichmentService()
    return _OSINT_SERVICE


def reset_osint_service() -> None:
    global _OSINT_SERVICE
    _OSINT_SERVICE = None
