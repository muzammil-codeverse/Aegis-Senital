from app.models.osint_models import CaseDocumentSummary, CaseEnrichmentAuditLog, CaseExternalSource
from app.repositories.osint_repository import JsonlOsintRepository


def _config(tmp_path):
    return {
        "osint_enrichment": {
            "enabled": True,
            "mode": "analyst_provided_only",
            "storage": {"jsonl_dir": str(tmp_path / "osint")},
        }
    }


def test_osint_repository_crud_and_summary_persistence(tmp_path):
    repository = JsonlOsintRepository(config=_config(tmp_path))
    source = repository.create_source(
        CaseExternalSource(
            case_id="case_1",
            source_type="analyst_note",
            title="Analyst note",
            description="Manual source context",
            created_by="operator",
        )
    )

    assert repository.get_source(source.source_id) is not None
    assert len(repository.list_sources("case_1")) == 1

    updated = repository.update_source(source.source_id, {"source_reliability": "medium"})
    assert updated.source_reliability == "medium"

    summary = repository.save_summary(
        CaseDocumentSummary(
            case_id="case_1",
            source_ids=[source.source_id],
            summary="Analyst-provided enrichment summary.",
            key_points=["Manual source"],
            source_references=[{"type": "external_source", "id": source.source_id, "label": "Analyst note"}],
            operator_review_caveat="Requires operator review.",
            limitations=["Not independently verified."],
        )
    )
    assert repository.list_summaries("case_1")[0].summary_id == summary.summary_id

    audit = repository.add_audit_log(
        CaseEnrichmentAuditLog(case_id="case_1", source_id=source.source_id, action="osint_source_created")
    )
    assert repository.list_audit_logs("case_1")[0].enrichment_audit_id == audit.enrichment_audit_id

    assert repository.delete_source(source.source_id) is True
    assert repository.get_source(source.source_id) is None
