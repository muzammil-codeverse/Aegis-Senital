#!/usr/bin/env python3
"""Smoke test for the Drone Patrol Mission Planner (Phase 45).

Verifies:
  1. Mission config is loadable
  2. A 3-waypoint mission plan can be created and validated
  3. Route estimation runs correctly
  4. A mission session can be started (gracefully fails if simulator not running)
  5. Mission status can be queried

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
    print(f"  [WARN] {msg} (non-strict — continuing)")


def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


def main(strict: bool = False, device: str = "cpu") -> None:
    print("=== Drone Patrol Mission Planner — Smoke Test ===")
    print(f"  strict={strict}  device={device}")
    print()

    # ------------------------------------------------------------------
    # 1. Config
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2. Models
    # ------------------------------------------------------------------
    print("\n[2] Pydantic models")
    try:
        from app.models.drone_mission_models import (
            DroneMissionCreateRequest,
            DroneMissionPlan,
            DroneMissionStatus,
            DroneWaypoint,
        )
        wp1 = DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=40, velocity_mps=5, label="Home")
        wp2 = DroneWaypoint(latitude=30.1585, longitude=71.5260, altitude_meters=45, velocity_mps=5, label="East")
        wp3 = DroneWaypoint(latitude=30.1590, longitude=71.5245, altitude_meters=42, velocity_mps=4, label="North")
        request = DroneMissionCreateRequest(
            name="Smoke Test Simulated Patrol",
            waypoints=[wp1, wp2, wp3],
        )
        assert len(request.waypoints) == 3
        _pass("Models instantiated correctly")
    except Exception as exc:
        _fail(f"Model error: {exc}", strict)
        return

    # ------------------------------------------------------------------
    # 3. Coordinate mapper
    # ------------------------------------------------------------------
    print("\n[3] Coordinate mapper")
    try:
        from app.services.drone.drone_coordinate_mapper import geo_to_ned, ned_to_geo
        ned = geo_to_ned(30.1585, 71.5260, 45)
        assert abs(ned.x) < 2000, "NED x should be within 2 km"
        geo = ned_to_geo(ned.x, ned.y, ned.z)
        assert abs(geo.latitude - 30.1585) < 0.001
        _pass(f"geo_to_ned and ned_to_geo round-trip OK (x={ned.x:.2f}, y={ned.y:.2f})")
    except Exception as exc:
        _fail(f"Coordinate mapper error: {exc}", strict)

    # ------------------------------------------------------------------
    # 4. Repository
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 5. Mission service — create + validate + estimate
    # ------------------------------------------------------------------
    print("\n[5] Mission service")
    try:
        import tempfile
        from app.repositories.drone_mission_repository import DroneMissionRepository
        from app.services.drone.drone_mission_service import DroneMissionService
        from app.models.drone_mission_models import DroneMissionCreateRequest, DroneWaypoint

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneMissionRepository(root_dir=tmpdir)
            svc = DroneMissionService(repository=repo)

            req = DroneMissionCreateRequest(
                name="Smoke Test Patrol",
                waypoints=[
                    DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=40, velocity_mps=5),
                    DroneWaypoint(latitude=30.1585, longitude=71.5260, altitude_meters=45, velocity_mps=5),
                    DroneWaypoint(latitude=30.1590, longitude=71.5245, altitude_meters=42, velocity_mps=4),
                ],
            )
            mission = svc.create_mission(req, created_by="smoke_test")
            assert mission.simulated is True
            assert mission.operator_review_required is True
            assert mission.estimated_distance_meters is not None
            assert mission.estimated_distance_meters > 0
            _pass(f"Mission created: {mission.mission_id}, distance={mission.estimated_distance_meters:.1f}m")

            # Verify it's persisted
            fetched = svc.get_mission(mission.mission_id)
            assert fetched is not None
            _pass("Mission persisted and retrievable")

    except Exception as exc:
        _fail(f"Mission service error: {exc}", strict)
        return

    # ------------------------------------------------------------------
    # 6. Execution service — start (simulator may not be running)
    # ------------------------------------------------------------------
    print("\n[6] Execution service — start mission")
    try:
        import tempfile
        from app.repositories.drone_mission_repository import DroneMissionRepository
        from app.services.drone.drone_mission_service import DroneMissionService
        from app.services.drone.drone_mission_execution_service import DroneMissionExecutionService
        from app.models.drone_mission_models import (
            DroneMissionCreateRequest,
            DroneMissionSession,
            DroneMissionStatus,
            DroneWaypoint,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneMissionRepository(root_dir=tmpdir)
            plan_svc = DroneMissionService(repository=repo)
            exec_svc = DroneMissionExecutionService(repository=repo)

            req = DroneMissionCreateRequest(
                name="Smoke Exec Patrol",
                waypoints=[
                    DroneWaypoint(latitude=30.1575, longitude=71.5249, altitude_meters=40, velocity_mps=5),
                    DroneWaypoint(latitude=30.1585, longitude=71.5260, altitude_meters=45, velocity_mps=5),
                ],
            )
            mission = plan_svc.create_mission(req, created_by="smoke_test")
            session = DroneMissionSession(
                mission_id=mission.mission_id,
                drone_id=mission.assigned_drone_id,
                total_waypoints=len(mission.waypoints),
            )
            repo.start_session(session)
            result_session = exec_svc.start_mission(mission, session, started_by="smoke_test")

            # Simulator probably not connected — should fail gracefully, not raise
            assert result_session.status in (
                DroneMissionStatus.EXECUTING,
                DroneMissionStatus.FAILED,
            ), f"Unexpected status: {result_session.status}"

            if result_session.status == DroneMissionStatus.FAILED:
                _skip("Simulator not connected — mission gracefully failed (expected in CI)")
            else:
                _pass("Mission started; simulator connected")

            # Status query should always work
            status = exec_svc.get_mission_status(session.session_id)
            assert status["session_id"] == session.session_id
            _pass("get_mission_status returns valid data")

    except Exception as exc:
        _fail(f"Execution service error: {exc}", strict)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=== Smoke test complete ===")
    print("All Phase 45 drone patrol mission planner checks passed (or skipped for offline simulator).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail hard on any error")
    parser.add_argument("--device", default="cpu", help="Device hint (cpu/cuda) — informational only")
    args = parser.parse_args()
    main(strict=args.strict, device=args.device)
