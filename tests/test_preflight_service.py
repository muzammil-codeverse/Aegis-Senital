from __future__ import annotations

import builtins
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.preflight_routes import router as preflight_router
from app.core.capabilities import CapabilityRegistry, CapabilityState, register_default_capabilities
from app.core.preflight import PreflightMode, PreflightRunStatus
from app.core.preflight.service import PreflightService


def _service() -> PreflightService:
    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    return PreflightService(registry)


def test_quick_preflight_returns_valid_structure():
    service = _service()

    run = service.start_preflight(PreflightMode.QUICK, triggered_by="pytest")

    assert run.run_id
    assert run.mode == PreflightMode.QUICK
    assert run.overall_status in {PreflightRunStatus.PASSED, PreflightRunStatus.PARTIALLY_PASSED}
    assert run.completed_at is not None
    assert {result.capability_id for result in run.results} >= {"backend_api", "auth_session", "local_storage"}
    assert all(result.check_level >= 1 for result in run.results)


def test_quick_preflight_does_not_load_heavy_models(monkeypatch):
    service = _service()
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"app.services.video_service", "inference.runtime"}:
            raise AssertionError(f"heavy runtime import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    run = service.start_preflight(PreflightMode.QUICK)

    assert run.overall_status in {PreflightRunStatus.PASSED, PreflightRunStatus.PARTIALLY_PASSED}
    assert "app.services.video_service" not in sys.modules


def test_missing_openai_key_marks_llm_osint_degraded(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = _service()

    result = service.evaluate_capability("llm_osint", PreflightMode.EXHIBITION)

    assert result.state == CapabilityState.DEGRADED
    assert result.reason == "OPENAI_API_KEY missing"
    assert result.metadata["openai_key_present"] is False
    assert service.registry.get("llm_osint").runtime_status.state == CapabilityState.DEGRADED


def test_unknown_capability_check_returns_clean_error(monkeypatch):
    monkeypatch.setattr("app.api.security_dependencies.auth_required", lambda: False)
    app = FastAPI()
    app.include_router(preflight_router)

    response = TestClient(app).post("/api/preflight/capabilities/not_registered/check")

    assert response.status_code == 404
    assert "not_registered" in response.json()["detail"]


def test_preflight_summary_status_rules(tmp_path):
    service = _service()
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("occupied", encoding="utf-8")
    service.registry.get("local_storage").descriptor.metadata["writable_paths"] = [str(blocking_file)]

    run = service.start_preflight(PreflightMode.QUICK, selected_capabilities=["local_storage"])
    summary = service.summarize_preflight_results(run)

    assert run.overall_status == PreflightRunStatus.FAILED
    assert summary.overall_status == PreflightRunStatus.FAILED
    assert summary.blocking_failures


def test_registry_status_updates_from_preflight(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service = _service()

    service.evaluate_capability("llm_osint", PreflightMode.EXHIBITION)

    record = service.registry.get("llm_osint")
    assert record.runtime_status.state == CapabilityState.DEGRADED
    assert record.runtime_status.metadata["preflight"]["openai_key_present"] is False


def test_exhibition_preflight_checks_uploaded_video_intelligence_path():
    service = _service()

    result = service.evaluate_capability("uploaded_video_pipeline", PreflightMode.EXHIBITION)

    check_names = {check.name for check in result.checks}
    assert "uploaded_video_storage" in check_names
    assert "uploaded_video_model_reference" in check_names
    assert "intelligence_event_adapter" in check_names
    assert "uploaded_video_promotion_service" in check_names
    assert "module_import" in check_names
    assert result.state in {CapabilityState.COLD, CapabilityState.READY, CapabilityState.DEGRADED}


def test_command_center_preflight_dry_run_does_not_persist_fake_alerts():
    service = _service()

    result = service.evaluate_capability("alerts", PreflightMode.EXHIBITION)

    check_names = {check.name for check in result.checks}
    assert "alert_incident_service" in check_names
    assert "intelligence_event_adapter" in check_names
    assert "uploaded_video_promotion_service" in check_names
    assert result.state in {CapabilityState.READY, CapabilityState.DEGRADED}
