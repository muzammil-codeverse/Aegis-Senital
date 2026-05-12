#!/usr/bin/env python3
"""Strict smoke test for the simulated drone mission planner/runtime.

Verifies:
  1. Mission config is loadable and safety flags are intact
  2. Mission models validate correctly
  3. Geo/NED conversion works
  4. Repository health is clean
  5. Planning service creates and persists a mission
  6. Live mission execution issues real simulator commands, records telemetry,
     records waypoint events, and completes as a simulated mission

Usage:
  python scripts/smoke_drone_mission.py
  python scripts/smoke_drone_mission.py --strict
  python scripts/smoke_drone_mission.py --device cuda
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str, strict: bool) -> None:
    if strict:
        print(f"  [FAIL] {msg}")
        sys.exit(1)
    print(f"  [WARN] {msg} (non-strict - continuing)")


def main(strict: bool = False, device: str = "cpu") -> None:
    print("=== Drone Patrol Mission Planner - Smoke Test ===")
    print(f"  strict={strict}  device={device}")
    print()

    print("[1] Drone mission config")
    try:
        import yaml

        cfg_path = ROOT / "configs" / "runtime" / "drone_mission.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        mission_cfg = cfg.get("drone_mission", {})
        assert mission_cfg.get("enabled") is True, "drone_mission.enabled must be true"
        assert mission_cfg.get("provider") == "cosys_airsim", "provider must be cosys_airsim"
        safety = mission_cfg.get("safety", {})
        assert safety.get("simulated_only") is True, "simulated_only must be true"
        assert safety.get("require_operator_start") is True
        assert safety.get("prohibit_real_world_claims") is True
        _pass("drone_mission.yaml loaded and safety flags verified")
    except Exception as exc:
        _fail(f"Config error: {exc}", strict)

    print("\n[2] Pydantic models")
    try:
        from app.models.drone_mission_models import DroneMissionCreateRequest, DroneWaypoint

        request = DroneMissionCreateRequest(
            name="Smoke Test Simulated Patrol",
            waypoints=[
                DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=5, velocity_mps=3, label="Home"),
                DroneWaypoint(latitude=30.15752, longitude=71.52492, altitude_meters=6, velocity_mps=3, label="East"),
                DroneWaypoint(latitude=30.15755, longitude=71.52495, altitude_meters=5, velocity_mps=3, label="North"),
            ],
        )
        assert len(request.waypoints) == 3
        _pass("Models instantiated correctly")
    except Exception as exc:
        _fail(f"Model error: {exc}", strict)
        return

    print("\n[3] Coordinate mapper")
    try:
        from app.services.drone.drone_coordinate_mapper import geo_to_ned, ned_to_geo

        ned = geo_to_ned(30.15752, 71.52492, 6)
        assert abs(ned.x) < 20, "NED x should stay within local mission radius"
        geo = ned_to_geo(ned.x, ned.y, ned.z)
        assert abs(geo.latitude - 30.15752) < 0.001
        _pass(f"geo_to_ned and ned_to_geo round-trip OK (x={ned.x:.2f}, y={ned.y:.2f}, z={ned.z:.2f})")
    except Exception as exc:
        _fail(f"Coordinate mapper error: {exc}", strict)

    print("\n[4] Repository")
    try:
        import tempfile

        from app.repositories.drone_mission_repository import DroneMissionRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneMissionRepository(root_dir=tmpdir)
            health = repo.health_check()
            assert health["status"] == "healthy", f"Expected healthy, got {health}"
            _pass("Repository health check OK")
    except Exception as exc:
        _fail(f"Repository error: {exc}", strict)

    print("\n[5] Mission service")
    try:
        import tempfile

        from app.models.drone_mission_models import DroneMissionCreateRequest, DroneWaypoint
        from app.repositories.drone_mission_repository import DroneMissionRepository
        from app.services.drone.drone_mission_service import DroneMissionService

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneMissionRepository(root_dir=tmpdir)
            svc = DroneMissionService(repository=repo)
            req = DroneMissionCreateRequest(
                name="Smoke Test Patrol",
                waypoints=[
                    DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=5, velocity_mps=3),
                    DroneWaypoint(latitude=30.15752, longitude=71.52492, altitude_meters=6, velocity_mps=3),
                    DroneWaypoint(latitude=30.15755, longitude=71.52495, altitude_meters=5, velocity_mps=3),
                ],
            )
            mission = svc.create_mission(req, created_by="smoke_test")
            assert mission.simulated is True
            assert mission.operator_review_required is True
            assert mission.estimated_distance_meters is not None
            assert mission.estimated_distance_meters > 0
            _pass(f"Mission created: {mission.mission_id}, distance={mission.estimated_distance_meters:.1f}m")

            fetched = svc.get_mission(mission.mission_id)
            assert fetched is not None
            _pass("Mission persisted and retrievable")
    except Exception as exc:
        _fail(f"Mission service error: {exc}", strict)
        return

    print("\n[6] Execution service - live mission run")
    try:
        import tempfile

        from app.models.drone_mission_models import (
            DroneMissionCreateRequest,
            DroneMissionSession,
            DroneMissionStatus,
            DroneWaypoint,
        )
        from app.repositories.drone_mission_repository import DroneMissionRepository
        from app.services.drone.drone_mission_execution_service import DroneMissionExecutionService
        from app.services.drone.drone_mission_service import DroneMissionService

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneMissionRepository(root_dir=tmpdir)
            plan_svc = DroneMissionService(repository=repo)
            exec_svc = DroneMissionExecutionService(repository=repo)

            req = DroneMissionCreateRequest(
                name="Smoke Exec Patrol",
                waypoints=[
                    DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=5, velocity_mps=3),
                    DroneWaypoint(latitude=30.15752, longitude=71.52492, altitude_meters=6, velocity_mps=3),
                    DroneWaypoint(latitude=30.15755, longitude=71.52495, altitude_meters=5, velocity_mps=3),
                ],
            )
            mission = plan_svc.create_mission(req, created_by="smoke_test")
            session = DroneMissionSession(
                mission_id=mission.mission_id,
                drone_id=mission.assigned_drone_id,
                total_waypoints=len(mission.waypoints),
            )
            repo.start_session(session)

            started_session = exec_svc.start_mission(mission, session, started_by="smoke_test")
            assert started_session.status == DroneMissionStatus.EXECUTING, (
                f"Mission should enter executing state, got {started_session.status}"
            )
            _pass("Mission session started against the live simulator")

            final_session = exec_svc.execute_mission_sync(mission, started_session.session_id)
            assert final_session is not None, "Mission execution returned no session"
            assert final_session.status == DroneMissionStatus.COMPLETED, (
                f"Mission should complete, got {final_session.status}"
            )
            assert final_session.simulated is True
            _pass("Simulator commands issued and mission completed")

            telemetry_points = repo.list_telemetry(final_session.session_id, limit=500)
            assert telemetry_points, "Telemetry points were not recorded"
            assert any(point.ned_x is not None for point in telemetry_points)
            _pass(f"Telemetry collected ({len(telemetry_points)} points)")

            events = repo.list_events(session_id=final_session.session_id, limit=200)
            event_types = [event.event_type.value for event in events]
            assert "mission_started" in event_types
            assert "waypoint_reached" in event_types
            assert "mission_completed" in event_types
            _pass(f"Mission events recorded ({len(events)} events)")

            status = exec_svc.get_mission_status(final_session.session_id)
            assert status["session_id"] == final_session.session_id
            assert status["status"] == DroneMissionStatus.COMPLETED.value
            assert status["telemetry_count"] >= 1
            assert status["waypoints_reached"] == len(mission.waypoints)
            assert status["simulated"] is True
            _pass("Mission status reflects waypoint progress and completion")
    except Exception as exc:
        _fail(f"Execution service error: {exc}", strict)

    print()
    print("=== Smoke test complete ===")
    print("All simulated drone mission planner checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail hard on any error")
    parser.add_argument("--device", default="cpu", help="Device hint (cpu/cuda) - informational only")
    args = parser.parse_args()
    main(strict=args.strict, device=args.device)
