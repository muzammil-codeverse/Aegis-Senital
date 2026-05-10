from pathlib import Path

import pytest

from app.models.osint_models import CaseExternalSource
from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from app.services.osint_file_service import OsintFileService
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


def _llm_config():
    return {
        "llm": {
            "enabled": True,
            "provider": "local_stub",
            "default_provider": "local_stub",
            "providers": {"local_stub": {"enabled": True}, "openai": {"enabled": False}},
            "safety": {"max_input_events": 100, "max_input_evidence_items": 100, "max_notes": 50},
            "reports": {"save_generated_reports": False},
        }
    }


def test_osint_summary_notes_remote_content_not_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr("app.services.osint_summary_service.get_llm_service", lambda: llm_service)

    source = CaseExternalSource(
        case_id="case_1",
        source_type="external_link",
        title="Manual source",
        url="https://example.com/page",
        description="Analyst supplied the title and short description only.",
        source_reliability="unknown",
        metadata={"domain": "example.com"},
    )

    summary = OsintSummaryService().summarize_sources(case_id="case_1", sources=[source], actor="operator")
    assert any("remote pages were not fetched" in item.lower() for item in summary.limitations)
    assert "independently verify identity" in summary.operator_review_caveat.lower()


def test_osint_upload_rejects_script_file(tmp_path):
    service = OsintFileService(
        config={
            "osint_enrichment": {
                "uploads": {
                    "enabled": True,
                    "storage_dir": str(tmp_path / "uploads"),
                    "max_file_size_mb": 1,
                    "allowed_extensions": [".txt", ".pdf"],
                }
            }
        }
    )

    with pytest.raises(ValueError, match="Rejected file type"):
        service.save_upload(
            case_id="case_1",
            source_id="src_1",
            filename="payload.ps1",
            content=b"Write-Host unsafe",
            content_type="text/plain",
            actor="operator",
        )
