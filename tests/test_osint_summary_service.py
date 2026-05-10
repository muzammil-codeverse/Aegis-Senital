from pathlib import Path

from app.models.osint_models import CaseExternalSource
from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from app.services.osint_summary_service import OSINT_OPERATOR_CAVEAT, OsintSummaryService


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _llm_config():
    return {
        "llm": {
            "enabled": True,
            "provider": "local_stub",
            "default_provider": "local_stub",
            "providers": {
                "local_stub": {"enabled": True},
                "openai": {"enabled": False},
            },
            "safety": {
                "max_input_events": 100,
                "max_input_evidence_items": 100,
                "max_notes": 50,
            },
            "reports": {"save_generated_reports": False},
        }
    }


def test_osint_summary_uses_uploaded_text_and_returns_grounded_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr("app.services.osint_summary_service.get_llm_service", lambda: llm_service)

    text_path = Path(tmp_path / "manual.txt")
    text_path.write_text("Analyst uploaded this text file with manual context.", encoding="utf-8")
    source = CaseExternalSource(
        case_id="case_1",
        source_type="uploaded_document",
        title="Manual document",
        description="Uploaded by analyst",
        storage_uri=str(text_path),
        source_reliability="medium",
        created_by="operator",
    )

    summary = OsintSummaryService().summarize_sources(case_id="case_1", sources=[source], actor="operator")

    assert summary.operator_review_caveat == OSINT_OPERATOR_CAVEAT
    assert summary.source_references
    assert summary.summary
    assert summary.provider == "local_stub"
    assert summary.model == "local_stub"
