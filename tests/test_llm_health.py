from app.repositories.case_repository import JsonlCaseRepository
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
            "enabled": True,
            "provider": "openai",
            "default_provider": "openai",
            "providers": {
                "local_stub": {"enabled": True},
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "model": "gpt-5.4-mini",
                    "escalation_model": "gpt-5.4",
                    "final_report_model": "gpt-5.5",
                    "reasoning": {
                        "default_effort": "low",
                        "escalation_effort": "medium",
                        "final_report_effort": "medium",
                    },
                    "cost_control": {
                        "max_input_tokens": 120000,
                        "max_output_tokens": 1800,
                        "allow_final_report_model": True,
                        "require_explicit_escalation": True,
                    },
                },
            },
            "development": {"allow_local_stub_if_openai_key_missing": True},
            "production": {
                "fail_if_enabled_provider_missing": True,
                "fail_if_openai_key_missing": True,
            },
        }
    }


def test_runtime_health_includes_llm_and_production_readiness_fails_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AEGIS_JWT_SECRET", "test-production-jwt-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr("app.services.case_service.get_case_service", lambda: case_service)
    monkeypatch.setattr("app.services.llm_service.get_llm_service", lambda: llm_service)

    health_service = RuntimeHealthService(config={"runtime": {"require_postgres": False}, "services": {}})
    report = health_service.get_health(include_sensitive=True)
    assert "llm" in report
    assert report["llm"]["status"] == "error"

    readiness = health_service.is_ready()
    assert readiness["ready"] is False
    assert any(failure.startswith("llm:") for failure in readiness["failures"])
