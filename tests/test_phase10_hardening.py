"""Phase 10 — Exhibition Demo hardening tests.

Tests:
 1. session_from_dict restores all fields correctly
 2. unknown status in persisted data is coerced to 'stale'
 3. load_persisted_session returns not_started when no file exists
 4. load_persisted_session marks running session stale if no active engine run
 5. auto_run_demo raises RuntimeError if called concurrently (lock)
 6. get_fallback_snapshot returns required keys with fallback=True
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service():
    """Fresh ExhibitionDemoService with isolated state dir."""
    from app.services.exhibition_demo_service import ExhibitionDemoService
    return ExhibitionDemoService()


def _fresh_engine():
    from app.services.scenario_engine_service import ScenarioEngineService
    return ScenarioEngineService()


# ---------------------------------------------------------------------------
# Test 1: from_dict restores all fields
# ---------------------------------------------------------------------------

def test_session_from_dict_restores_fields():
    from app.services.exhibition_demo_service import ExhibitionDemoSession

    data = {
        "demo_id": "demo-abc",
        "status": "running",
        "scenario_run_id": "run-xyz",
        "current_step": 3,
        "total_steps": 12,
        "active_alert_ids": ["alert-1", "alert-2"],
        "active_incident_ids": ["inc-1"],
        "assigned_drone_ids": ["DRONE-ALPHA"],
        "tracking_ready": True,
        "command_center_ready": True,
        "started_at": "2026-05-20T10:00:00+00:00",
        "completed_at": None,
        "last_error": None,
        "metadata": {"phase": 10},
    }

    s = ExhibitionDemoSession.from_dict(data)

    assert s.demo_id == "demo-abc"
    assert s.status == "running"
    assert s.scenario_run_id == "run-xyz"
    assert s.current_step == 3
    assert s.total_steps == 12
    assert s.active_alert_ids == ["alert-1", "alert-2"]
    assert s.active_incident_ids == ["inc-1"]
    assert s.assigned_drone_ids == ["DRONE-ALPHA"]
    assert s.tracking_ready is True
    assert s.command_center_ready is True
    assert s.metadata == {"phase": 10}


# ---------------------------------------------------------------------------
# Test 2: unknown status coerced to 'stale'
# ---------------------------------------------------------------------------

def test_session_from_dict_unknown_status_becomes_stale():
    from app.services.exhibition_demo_service import ExhibitionDemoSession

    s = ExhibitionDemoSession.from_dict({"status": "corrupted_garbage"})
    assert s.status == "stale"


# ---------------------------------------------------------------------------
# Test 3: load_persisted_session returns not_started when file absent
# ---------------------------------------------------------------------------

def test_load_persisted_session_no_file(tmp_path, monkeypatch):
    import app.services.exhibition_demo_service as svc_module

    # Point state dir to an empty tmp dir (no file)
    monkeypatch.setattr(svc_module, "_DEMO_STATE_DIR", tmp_path)
    monkeypatch.setattr(svc_module, "_SESSION_FILE", tmp_path / "demo_session.json")

    from app.services.exhibition_demo_service import ExhibitionDemoService
    svc = ExhibitionDemoService.__new__(ExhibitionDemoService)
    import threading
    svc._lock = threading.RLock()
    svc._autorun_lock = threading.Lock()
    tmp_path.mkdir(parents=True, exist_ok=True)
    session = svc._load_persisted_session()

    assert session.status == "not_started"


# ---------------------------------------------------------------------------
# Test 4: running session marked stale when engine has no matching run
# ---------------------------------------------------------------------------

def test_load_persisted_session_running_becomes_stale(tmp_path, monkeypatch):
    import app.services.exhibition_demo_service as svc_module

    # Write a session file with status=running but no matching engine run
    session_data = {
        "demo_id": "demo-stale",
        "status": "running",
        "scenario_run_id": "run-old-that-doesnt-exist",
        "current_step": 2,
        "total_steps": 12,
        "active_alert_ids": [],
        "active_incident_ids": [],
        "assigned_drone_ids": [],
        "tracking_ready": False,
        "command_center_ready": False,
        "started_at": "2026-05-19T10:00:00+00:00",
        "completed_at": None,
        "last_error": None,
        "metadata": {},
    }
    session_file = tmp_path / "demo_session.json"
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    monkeypatch.setattr(svc_module, "_DEMO_STATE_DIR", tmp_path)
    monkeypatch.setattr(svc_module, "_SESSION_FILE", session_file)

    # Use a fresh engine with no active run
    fresh_engine = _fresh_engine()
    monkeypatch.setattr(svc_module, "get_scenario_engine", lambda: fresh_engine, raising=False)

    from app.services.exhibition_demo_service import ExhibitionDemoService
    svc = ExhibitionDemoService.__new__(ExhibitionDemoService)
    import threading
    svc._lock = threading.RLock()
    svc._autorun_lock = threading.Lock()
    session = svc._load_persisted_session()

    # No matching active run → should be marked stale
    assert session.status == "stale"
    assert session.last_error is not None


# ---------------------------------------------------------------------------
# Test 5: auto_run_demo raises RuntimeError when called concurrently
# ---------------------------------------------------------------------------

def test_auto_run_concurrency_lock(monkeypatch):
    svc = _fresh_service()
    engine = _fresh_engine()
    monkeypatch.setattr("app.services.exhibition_demo_service.get_scenario_engine", lambda: engine, raising=False)

    svc.reset_demo()
    svc.start_demo(mode="step", run_preflight=False)

    # Acquire the lock manually to simulate a running auto-run
    acquired = svc._autorun_lock.acquire(blocking=False)
    assert acquired, "Lock should not be held yet"

    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            svc.auto_run_demo()
    finally:
        svc._autorun_lock.release()


# ---------------------------------------------------------------------------
# Test 6: get_fallback_snapshot returns required keys with fallback=True
# ---------------------------------------------------------------------------

def test_fallback_snapshot_returns_required_keys():
    svc = _fresh_service()
    snap = svc.get_fallback_snapshot()

    assert "demo_session" in snap
    assert "fallback_data" in snap
    assert "analytics_summary" in snap
    assert "ui_links" in snap

    fallback = snap["fallback_data"]
    assert fallback.get("fallback") is True
    assert "fallback_label" in fallback
    assert "scenario_id" in fallback
    assert fallback["scenario_id"] == "bank_robbery_demo"
    assert "timeline_summary" in fallback
    assert isinstance(fallback["timeline_summary"], list)
    assert len(fallback["timeline_summary"]) > 0
    assert fallback.get("simulated") is True
