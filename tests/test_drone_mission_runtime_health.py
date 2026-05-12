"""Tests for drone mission runtime health integration (Phase 45)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)


class TestDroneMissionMetrics:
    def test_metrics_have_mission_counters(self):
        from inference.monitoring.metrics import SystemMetrics
        m = SystemMetrics()
        assert hasattr(m, "drone_missions_created_total")
        assert hasattr(m, "drone_missions_started_total")
        assert hasattr(m, "drone_missions_completed_total")
        assert hasattr(m, "drone_missions_failed_total")
        assert hasattr(m, "drone_mission_waypoints_reached_total")
        assert hasattr(m, "drone_mission_telemetry_points_total")
        assert hasattr(m, "drone_mission_events_total")
        assert hasattr(m, "drone_mission_active_sessions")

    def test_increment_mission_counter(self):
        from inference.monitoring.metrics import SystemMetrics
        m = SystemMetrics()
        m.increment("drone_missions_created_total")
        assert m.drone_missions_created_total == 1


class TestRuntimeHealthService:
    def test_health_includes_drone_mission_block(self):
        from app.services.runtime_health_service import get_runtime_health_service
        svc = get_runtime_health_service()
        health = svc.get_health()
        assert "drone_mission" in health or "drone_mission" in str(health)

    def test_drone_mission_health_block(self):
        from app.services.runtime_health_service import RuntimeHealthService
        svc = RuntimeHealthService(config={"runtime": {}, "services": {}})
        result = svc._check_drone_mission()
        assert isinstance(result, dict)
        assert result.get("simulated_only") is True
        assert "status" in result


class TestValidateRuntime:
    def test_drone_mission_config_in_config_list(self):
        import subprocess
        # Just verify config exists (the validation function itself is tested separately)
        cfg_path = ROOT / "configs" / "runtime" / "drone_mission.yaml"
        assert cfg_path.exists()
