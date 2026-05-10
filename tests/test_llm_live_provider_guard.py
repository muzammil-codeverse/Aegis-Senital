from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService


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
                    "model_env": "OPENAI_LLM_MODEL",
                    "escalation_model_env": "OPENAI_LLM_ESCALATION_MODEL",
                    "final_report_model_env": "OPENAI_LLM_FINAL_REPORT_MODEL",
                    "model": "gpt-5.4-mini",
                    "escalation_model": "gpt-5.4",
                    "final_report_model": "gpt-5.5",
                    "reasoning": {
                        "default_effort": "low",
                        "escalation_effort": "medium",
                        "final_report_effort": "medium",
                    },
                    "cost_control": {
                        "max_output_tokens": 1800,
                        "allow_final_report_model": True,
                        "require_explicit_escalation": True,
                    },
                },
            },
            "development": {"allow_local_stub_if_openai_key_missing": False},
            "production": {
                "fail_if_enabled_provider_missing": True,
                "fail_if_openai_key_missing": True,
            },
        }
    }


class FakeOpenAiProvider:
    def __init__(self, *, should_fail=False):
        self.calls = []
        self.should_fail = should_fail

    def verify_model(self, model_name: str, *, reasoning_effort: str = "low"):
        self.calls.append((model_name, reasoning_effort))
        if self.should_fail:
            raise RuntimeError("upstream 404 model_not_found")
        return {"model": model_name, "status": "ok", "response_preview": "Model available."}


def test_llm_verify_provider_uses_env_selected_models(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_LLM_ESCALATION_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_LLM_FINAL_REPORT_MODEL", "gpt-5.5")
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    service = LlmService(config=_llm_config(), case_service=case_service)
    provider = FakeOpenAiProvider()
    monkeypatch.setattr(service, "_get_provider", lambda name: provider)

    result = service.verify_provider(include_escalation=True)

    assert result["status"] == "ok"
    assert [item["model"] for item in result["models_checked"]] == ["gpt-5.4-mini", "gpt-5.4"]
    assert provider.calls == [("gpt-5.4-mini", "low"), ("gpt-5.4", "medium")]


def test_llm_verify_provider_reports_exact_model_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr(service, "_get_provider", lambda name: FakeOpenAiProvider(should_fail=True))

    result = service.verify_provider()

    assert result["status"] == "error"
    assert "gpt-5.4-mini" in result["detail"]
    assert "model_not_found" in result["detail"]
