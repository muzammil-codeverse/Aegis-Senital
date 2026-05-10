from app.repositories.case_repository import JsonlCaseRepository
from app.repositories.osint_repository import JsonlOsintRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from backend.app.services.runtime_health_service import RuntimeHealthService


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
            "enabled": False,
            "provider": "local_stub",
            "default_provider": "local_stub",
            "providers": {"local_stub": {"enabled": True}},
        }
    }


def test_runtime_health_includes_osint_and_readiness_fails_when_enabled_storage_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    broken_repo = JsonlOsintRepository(config={"osint_enrichment": {"enabled": True, "storage": {"jsonl_dir": str(tmp_path / "osint")}}})
    broken_repo._set_error("storage unavailable")

    class BrokenOsintService:
        def health(self):
            return broken_repo.health()

    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    monkeypatch.setattr("app.services.llm_service.get_llm_service", lambda: llm_service)
    monkeypatch.setattr("app.services.osint_service.get_osint_service", lambda: BrokenOsintService())

    health_service = RuntimeHealthService(config={"runtime": {"require_postgres": False}, "services": {}})
    report = health_service.get_health(include_sensitive=True)
    assert "osint_enrichment" in report
    assert report["osint_enrichment"]["enabled"] is True

    readiness = health_service.is_ready()
    assert readiness["ready"] is False
    assert any(failure.startswith("osint_enrichment:") for failure in readiness["failures"])
