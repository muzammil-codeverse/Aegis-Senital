from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.osint_repository import JsonlOsintRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from app.services.osint_service import OsintEnrichmentService
from app.services.osint_summary_service import OsintSummaryService


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _osint_config(tmp_path):
    return {
        "osint_enrichment": {
            "enabled": True,
            "mode": "analyst_provided_only",
            "storage": {"jsonl_dir": str(tmp_path / "osint")},
            "uploads": {
                "enabled": True,
                "storage_dir": str(tmp_path / "uploads"),
                "max_file_size_mb": 5,
                "allowed_extensions": [".txt", ".pdf", ".png", ".jpg", ".jpeg", ".md", ".json", ".csv"],
            },
            "links": {"enabled": True, "require_manual_entry": True, "fetch_preview": False, "fetch_full_page": False},
            "audit": {"log_all_enrichment_actions": True},
            "llm": {"summarize_uploaded_text": True, "summarize_external_link_metadata": True},
        }
    }


def _llm_config():
    return {
        "llm": {
            "enabled": True,
            "provider": "local_stub",
            "default_provider": "local_stub",
            "providers": {"local_stub": {"enabled": True}, "openai": {"enabled": False}},
            "safety": {"max_input_events": 100, "max_input_evidence_items": 100, "max_notes": 50},
            "reports": {
                "default_format": "markdown",
                "include_evidence_ids": True,
                "include_case_ids": True,
                "include_model_caveats": True,
                "include_timeline": True,
                "save_generated_reports": True,
            },
        }
    }


def test_case_timeline_export_and_llm_include_enrichment(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    osint_service = OsintEnrichmentService(
        repository=JsonlOsintRepository(config=_osint_config(tmp_path)),
        config=_osint_config(tmp_path),
        summary_service=OsintSummaryService(config=_osint_config(tmp_path)),
    )
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    monkeypatch.setattr("app.services.osint_service.get_osint_service", lambda: osint_service)
    monkeypatch.setattr("app.services.osint_summary_service.get_llm_service", lambda: llm_service)

    case = case_service.create_case({"title": "Possible enrichment integration case"}, actor="operator")
    source = osint_service.create_source(
        case.case_id,
        {
            "source_type": "analyst_note",
            "title": "Analyst note",
            "description": "Manual source for integration testing.",
            "source_reliability": "medium",
            "metadata": {},
        },
        actor="operator",
    )
    osint_service.summarize(case.case_id, [source.source_id], actor="operator")

    timeline = case_service.get_timeline(case.case_id)
    assert any(item.type == "enrichment_source_added" for item in timeline)
    assert any(item.type == "enrichment_summary_generated" for item in timeline)

    exported = case_service.export_case(case.case_id, format="markdown", actor="operator")
    assert "Analyst-Provided Enrichment" in exported.content
    assert "Enrichment Summaries" in exported.content

    summary = llm_service.summarize_case(case.case_id, {"summary_kind": "case_summary"}, actor="operator")
    assert any(source_ref.type == "external_source" for source_ref in summary.sources)
    assert summary.content.startswith("This report is an automated decision-support draft")
