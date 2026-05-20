from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.scenario_models import ScenarioState, ActorRole
from app.services.scenario_engine_service import (
    BANK_ROBBERY_DEMO,
    SCENARIO_CATALOGUE,
    ScenarioEngineService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> ScenarioEngineService:
    return ScenarioEngineService()


# ---------------------------------------------------------------------------
# Part A: Scenario catalogue
# ---------------------------------------------------------------------------


def test_bank_robbery_demo_in_catalogue():
    assert "bank_robbery_demo" in SCENARIO_CATALOGUE


def test_bank_robbery_demo_has_four_actors():
    assert len(BANK_ROBBERY_DEMO.actors) == 4


def test_bank_robbery_demo_actor_roles_cover_required_types():
    roles = {a.actor_id: a.role for a in BANK_ROBBERY_DEMO.actors}
    assert "SUSPECT-001" in roles
    assert roles["SUSPECT-001"] == ActorRole.SUSPECT
    assert "ESCAPE-VEHICLE-001" in roles
    assert roles["ESCAPE-VEHICLE-001"] == ActorRole.VEHICLE


def test_bank_robbery_demo_has_twelve_timeline_events():
    assert len(BANK_ROBBERY_DEMO.timeline) == 12


def test_bank_robbery_demo_weapon_detected_event_at_step_3():
    weapon_events = [e for e in BANK_ROBBERY_DEMO.timeline if e.event_type == "weapon_detected"]
    assert len(weapon_events) == 1
    assert weapon_events[0].step == 3
    assert weapon_events[0].t_offset_seconds == 15
    assert weapon_events[0].promote_to_alert is True
    assert weapon_events[0].promote_to_incident is True
    assert weapon_events[0].trigger_drone_dispatch is True


def test_bank_robbery_demo_uses_phase5_cameras():
    camera_ids = set(BANK_ROBBERY_DEMO.camera_ids)
    for expected in ("CAM-BANK-01", "CAM-BANK-02", "CAM-PARKING-01", "CAM-ALLEY-01"):
        assert expected in camera_ids, f"Expected camera {expected} in scenario"


def test_bank_robbery_demo_uses_drone_alpha():
    assert "DRONE-ALPHA" in BANK_ROBBERY_DEMO.drone_ids


# ---------------------------------------------------------------------------
# Part B: ScenarioEngineService — start, step, state
# ---------------------------------------------------------------------------


def test_engine_starts_scenario_in_step_mode():
    engine = _engine()
    run = engine.start("bank_robbery_demo", mode="step")
    assert run.state == ScenarioState.RUNNING
    assert run.mode == "step"
    assert run.current_step == 0
    assert run.total_steps == 12


def test_engine_step_advances_current_step():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    result = engine.step()
    assert result["status"] == "ok"
    assert result["step"] == 0
    run = engine.active_run()
    assert run.current_step == 1


def test_engine_step_generates_observation():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    result = engine.step()
    obs = result.get("observation")
    assert obs is not None
    assert obs.get("event_type") == "person_tracking"


def test_engine_pause_and_resume():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    status = engine.pause()
    assert status.state == ScenarioState.PAUSED
    status = engine.resume()
    assert status.state == ScenarioState.RUNNING


def test_engine_cancel_transitions_to_cancelled():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    status = engine.cancel()
    assert status.state == ScenarioState.CANCELLED


# ---------------------------------------------------------------------------
# Part C: Drone dispatch on weapon_detected
# ---------------------------------------------------------------------------


def test_drone_dispatched_on_weapon_detected_step(tmp_path):
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    # Step to step 3 (weapon_detected at t+15s)
    for _ in range(4):
        engine.step()
    run = engine.active_run()
    assert run.drone_dispatched is True
    assert run.dispatched_drone_id == "DRONE-ALPHA"


# ---------------------------------------------------------------------------
# Part D: Auto-run mode
# ---------------------------------------------------------------------------


def test_engine_auto_run_completes_all_steps():
    engine = _engine()
    run = engine.start("bank_robbery_demo", mode="auto")
    assert run.state == ScenarioState.COMPLETED
    assert run.current_step == 12
    assert run.observations_generated == 12


def test_engine_auto_run_promotes_alerts_and_incidents():
    engine = _engine()
    run = engine.start("bank_robbery_demo", mode="auto")
    # Events at step 3 and step 11 both promote
    assert run.alerts_promoted >= 2
    assert run.incidents_promoted >= 2


# ---------------------------------------------------------------------------
# Part E: Observation timeline
# ---------------------------------------------------------------------------


def test_observation_timeline_populated_after_steps():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    engine.step()
    engine.step()
    timeline = engine.run_observation_timeline()
    assert len(timeline) == 2
    assert timeline[0]["step"] == 0
    assert timeline[1]["step"] == 1


def test_reset_clears_active_run():
    engine = _engine()
    engine.start("bank_robbery_demo", mode="step")
    engine.reset()
    assert engine.active_run() is None
    assert engine.active_run_status() is None
