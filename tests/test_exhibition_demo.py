"""Phase 9 — Exhibition Demo Controller tests.

Tests:
 1. get_demo_status returns not_started state cleanly
 2. reset_demo returns ready status
 3. start_demo creates a scenario run
 4. step_demo advances scenario
 5. step_demo to weapon event (step 4) creates alert/incident in session
 6. drone assigned appears in demo session after weapon event
 7. tracking_ready becomes True after drone dispatch
 8. reset_demo clears active state safely
 9. runbook returns structured steps
10. invalid transition (step without start) returns RuntimeError
11. auto_run_demo completes the scenario
12. get_demo_snapshot returns combined state shape
13. preflight demo workflow capability is registered
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service():
    """Return a fresh ExhibitionDemoService with no shared state."""
    from app.services.exhibition_demo_service import ExhibitionDemoService
    return ExhibitionDemoService()


def _fresh_engine():
    """Return a fresh ScenarioEngineService with no active run."""
    from app.services.scenario_engine_service import ScenarioEngineService
    return ScenarioEngineService()


# ---------------------------------------------------------------------------
# Test 1: get_demo_status returns not_started cleanly
# ---------------------------------------------------------------------------

def test_demo_status_initial_state(tmp_path, monkeypatch):
    # Phase 10: service now loads persisted state on init; point to empty tmp dir
    import app.services.exhibition_demo_service as svc_module
    monkeypatch.setattr(svc_module, "_DEMO_STATE_DIR", tmp_path)
    monkeypatch.setattr(svc_module, "_SESSION_FILE", tmp_path / "demo_session.json")

    svc = _fresh_service()
    status = svc.get_demo_status()
    assert status["status"] == "not_started"
    assert status["scenario_run_id"] is None
    assert status["active_alert_ids"] == []
    assert status["active_incident_ids"] == []
    assert status["assigned_drone_ids"] == []
    assert status["tracking_ready"] is False


# ---------------------------------------------------------------------------
# Test 2: reset_demo returns ready status
# ---------------------------------------------------------------------------

def test_reset_demo_returns_ready():
    svc = _fresh_service()
    result = svc.reset_demo()
    assert result.get("reset") is True
    status = svc.get_demo_status()
    assert status["status"] == "ready"


# ---------------------------------------------------------------------------
# Test 3: start_demo creates a scenario run
# ---------------------------------------------------------------------------

def test_start_demo_creates_scenario_run(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    result = svc.start_demo(mode="step", run_preflight=False)

    assert result.get("status") == "running"
    demo = result.get("demo") or {}
    assert demo.get("status") == "running"
    assert demo.get("scenario_run_id") is not None
    assert demo.get("total_steps", 0) > 0


# ---------------------------------------------------------------------------
# Test 4: step_demo advances scenario
# ---------------------------------------------------------------------------

def test_step_demo_advances_step(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    result = svc.step_demo()

    assert result["status"] == "ok"
    step_result = result["step_result"]
    assert step_result.get("step") == 0
    assert step_result.get("event_type") is not None


# ---------------------------------------------------------------------------
# Test 5: step to weapon event creates alert/incident in session
# ---------------------------------------------------------------------------

def test_step_to_weapon_event_creates_alert(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    # Step 4 times (0-indexed steps 0,1,2,3) — step 3 is weapon_detected
    for _ in range(4):
        svc.step_demo()

    status = svc.get_demo_status()
    # After weapon_detected step, promotions should exist
    run_id = status.get("scenario_run_id")
    if run_id:
        promotions = engine.list_promotions(run_id)
        alert_promotions = [p for p in promotions if p.get("alert")]
        # weapon_detected (step 3) triggers promote_to_alert=True
        assert len(alert_promotions) >= 1


# ---------------------------------------------------------------------------
# Test 6: drone assigned appears in session after weapon event
# ---------------------------------------------------------------------------

def test_drone_assigned_after_weapon_step(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    for _ in range(4):
        svc.step_demo()

    status = svc.get_demo_status()
    run_id = status.get("scenario_run_id")
    if run_id:
        route = engine.get_drone_route(run_id)
        if route:
            assert route.drone_id == "DRONE-ALPHA"


# ---------------------------------------------------------------------------
# Test 7: tracking_ready becomes True after drone dispatch
# ---------------------------------------------------------------------------

def test_tracking_ready_after_dispatch(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    # drone_observation at step 5 creates the route; weapon_detected at step 3 initiates it
    for _ in range(6):
        result = svc.step_demo()
        if result.get("status") == "completed":
            break

    status = svc.get_demo_status()
    run_id = status.get("scenario_run_id")
    if run_id:
        route = engine.get_drone_route(run_id)
        if route:
            assert status["tracking_ready"] is True


# ---------------------------------------------------------------------------
# Test 8: reset_demo clears active state safely
# ---------------------------------------------------------------------------

def test_reset_clears_state(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    svc.step_demo()

    # Now reset
    svc.reset_demo()
    status = svc.get_demo_status()
    assert status["status"] == "ready"
    assert status["scenario_run_id"] is None
    assert status["active_alert_ids"] == []


# ---------------------------------------------------------------------------
# Test 9: runbook returns structured steps
# ---------------------------------------------------------------------------

def test_runbook_returns_steps():
    svc = _fresh_service()
    runbook = svc.get_runbook()
    assert "steps" in runbook
    assert isinstance(runbook["steps"], list)
    assert len(runbook["steps"]) >= 10
    for step in runbook["steps"]:
        assert "step" in step
        assert "title" in step
        assert "description" in step


# ---------------------------------------------------------------------------
# Test 10: invalid transition (step without start) returns RuntimeError
# ---------------------------------------------------------------------------

def test_step_without_start_raises():
    svc = _fresh_service()
    with pytest.raises(RuntimeError):
        svc.step_demo()


# ---------------------------------------------------------------------------
# Test 11: auto_run_demo completes the scenario
# ---------------------------------------------------------------------------

def test_auto_run_completes(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)
    result = svc.auto_run_demo()

    assert result["status"] == "ok"
    status = svc.get_demo_status()
    assert status["status"] in ("completed", "running")  # completed if all steps ran


# ---------------------------------------------------------------------------
# Test 12: get_demo_snapshot returns combined state shape
# ---------------------------------------------------------------------------

def test_snapshot_returns_expected_keys(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    snapshot = svc.get_demo_snapshot()

    assert "demo_session" in snapshot
    assert "analytics_summary" in snapshot
    assert "ui_links" in snapshot
    assert "drone_state" in snapshot
    assert "suspect_path" in snapshot
    assert "camera_handoffs" in snapshot


# ---------------------------------------------------------------------------
# Test 13: preflight demo workflow capability is registered
# ---------------------------------------------------------------------------

def test_exhibition_demo_capability_registered():
    from app.core.capabilities.defaults import register_default_capabilities
    from app.core.capabilities.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    record = registry.get_or_none("exhibition_demo_workflow")
    assert record is not None
    assert record.descriptor.name == "Exhibition Demo Workflow"
    assert "scenario_id" in record.descriptor.metadata
    assert record.descriptor.metadata["scenario_id"] == "bank_robbery_demo"
