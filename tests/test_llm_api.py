from fastapi.testclient import TestClient

from app.api import case_routes as case_routes_module
from app.api import llm_routes as llm_routes_module
from app.models.security_models import UserAccount
from app.repositories.case_repository import JsonlCaseRepository
from app.services import auth_service as auth_module
from app.services import case_service as case_service_module
from app.services.case_service import CaseService
from app.services.llm_service import LlmService
from main import app


def _case_config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 10},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def _llm_config():
    return {
        "llm": {
            "enabled": True,
            "provider": "openai",
            "mode": "assistive_only",
            "default_provider": "openai",
            "providers": {
                "local_stub": {"enabled": True},
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "model": "gpt-5.4-mini",
                    "escalation_model": "gpt-5.4",
                    "final_report_model": "gpt-5.5",
                    "timeout_seconds": 45,
                    "max_retries": 0,
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
            "safety": {
                "max_input_events": 100,
                "max_input_evidence_items": 100,
                "max_notes": 50,
            },
            "reports": {
                "default_format": "markdown",
                "include_evidence_ids": True,
                "include_case_ids": True,
                "include_model_caveats": True,
                "include_timeline": True,
                "save_generated_reports": True,
            },
            "development": {"allow_local_stub_if_openai_key_missing": True},
            "production": {
                "fail_if_enabled_provider_missing": True,
                "fail_if_openai_key_missing": True,
            },
        }
    }


def _user(role: str, metadata: dict | None = None) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
        metadata=metadata or {},
    )


def _install_auth(monkeypatch):
    users = {
        "admin": _user("admin"),
        "supervisor": _user("supervisor"),
        "operator": _user("operator"),
        "viewer": _user("viewer"),
    }
    service = auth_module.get_auth_service()
    monkeypatch.setattr(service, "get_current_user_from_token", lambda token: users.get(token))
    return users


def test_llm_endpoints_use_local_stub_and_persist_reports(tmp_path, monkeypatch):
    users = _install_auth(monkeypatch)
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr(case_routes_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(llm_routes_module, "get_llm_service", lambda: llm_service)

    case = case_service.create_case({"title": "Possible anomaly incident", "severity": "high", "priority": "high"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    case_service.add_evidence(case.case_id, {"evidence_type": "event", "title": "Linked event", "description": "Observed event evidence."}, actor="operator")

    client = TestClient(app, raise_server_exceptions=False)

    status = client.get("/api/llm/status", headers={"Authorization": "Bearer viewer"})
    assert status.status_code == 200
    assert status.json()["item"]["active_provider"] == "local_stub"

    summary = client.post(
        f"/api/llm/cases/{case.case_id}/summary",
        headers={"Authorization": "Bearer operator"},
        json={"summary_kind": "case_summary"},
    )
    assert summary.status_code == 200
    assert summary.json()["item"]["provider"] == "local_stub"
    assert summary.json()["item"]["content"].startswith("This report is an automated decision-support draft")
    assert summary.json()["item"]["sources"]

    report = client.post(
        f"/api/llm/cases/{case.case_id}/report",
        headers={"Authorization": "Bearer operator"},
        json={"report_kind": "draft_case_report"},
    )
    assert report.status_code == 200
    assert report.json()["item"]["report_id"]
    stored_report = case_service.repository.list_reports(case.case_id)[0]
    assert stored_report.report_type == "draft_case_report"

    query = client.post(
        f"/api/llm/cases/{case.case_id}/query",
        headers={"Authorization": "Bearer operator"},
        json={"question": "What does the evidence currently show?"},
    )
    assert query.status_code == 200
    assert query.json()["item"]["content"].startswith("This report is an automated decision-support draft")


def test_llm_permissions_and_missing_key_verification_message(tmp_path, monkeypatch):
    users = _install_auth(monkeypatch)
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    case_service = CaseService(repository=JsonlCaseRepository(config=_case_config(tmp_path)), config=_case_config(tmp_path))
    llm_service = LlmService(config=_llm_config(), case_service=case_service)
    monkeypatch.setattr(case_routes_module, "get_case_service", lambda: case_service)
    monkeypatch.setattr(llm_routes_module, "get_llm_service", lambda: llm_service)

    case = case_service.create_case({"title": "Possible restricted-zone incident"}, actor="operator")
    users["operator"].metadata = {"case_scopes": [case.case_id]}
    client = TestClient(app, raise_server_exceptions=False)

    denied = client.post(
        f"/api/llm/cases/{case.case_id}/summary",
        headers={"Authorization": "Bearer viewer"},
        json={"summary_kind": "case_summary"},
    )
    assert denied.status_code == 403

    verification = client.post(
        "/api/llm/verify-provider",
        headers={"Authorization": "Bearer operator"},
        json={},
    )
    assert verification.status_code == 200
    assert verification.json()["item"]["detail"] == "OpenAI provider not verified because OPENAI_API_KEY is missing."
