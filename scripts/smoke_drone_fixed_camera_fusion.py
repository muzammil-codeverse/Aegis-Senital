#!/usr/bin/env python3
"""Phase 46/47 drone + fixed camera fusion smoke test.

Deterministic mode seeds known observations and validates the fusion service.
Live mode pulls real telemetry/frame data from the prepared Cosys-AirSim runtime,
then correlates that live simulated drone observation with a nearby fixed-camera
anchor observation using the same safe wording guarantees as production code.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _check(name: str, ok: bool, detail: str = "", required: bool = True) -> bool:
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_deterministic_smoke() -> bool:
    print("[Deterministic Fusion Smoke]")
    results = []

    try:
        from app.models.drone_fusion_models import FORBIDDEN_PHRASES, FusionObservation, FusionSourceRef
        from app.repositories.drone_fusion_repository import DroneFusionRepository
        from app.services.drone_fusion.fusion_service import CrossSourceFusionService

        results.append(_check("imports OK", True))
    except Exception as exc:
        results.append(_check("imports OK", False, str(exc)))
        return False

    repo = DroneFusionRepository(root_dir="storage/drone_fusion_smoke_test")
    ts = _now_iso()

    fixed_cam_obs = FusionObservation(
        source_type="fixed_camera",
        source_id="cam_01",
        event_id="evt_smoke_001",
        case_id="case_smoke_001",
        timestamp=ts,
        latitude=30.1575,
        longitude=71.5249,
        geo_missing=False,
        event_type="weapon_detected",
        severity="high",
        simulated=False,
        evidence_refs=["evt_smoke_001"],
        source_ref=FusionSourceRef(
            source_type="fixed_camera",
            source_id="cam_01",
            event_id="evt_smoke_001",
            simulated=False,
        ),
    )

    drone_obs = FusionObservation(
        source_type="drone_simulation",
        source_id="drone_sim_01",
        event_id="evt_smoke_002",
        case_id="case_smoke_001",
        timestamp=ts,
        latitude=30.1577,
        longitude=71.5251,
        altitude_meters=50.0,
        geo_missing=False,
        event_type="weapon_detected",
        severity="high",
        simulated=True,
        evidence_refs=["evt_smoke_002"],
        source_ref=FusionSourceRef(
            source_type="drone_simulation",
            source_id="drone_sim_01",
            event_id="evt_smoke_002",
            simulated=True,
        ),
    )

    repo.save_observation(fixed_cam_obs)
    repo.save_observation(drone_obs)
    results.append(_check("2 observations seeded", True))

    class _DummyUser:
        username = "smoke_test"
        role = "admin"
        user_id = "smoke_user"

    svc = CrossSourceFusionService(repo)
    correlations = svc.correlate(
        [fixed_cam_obs, drone_obs],
        user=_DummyUser(),
        case_id="case_smoke_001",
        event_id="evt_smoke_001",
    )

    results.append(_check("correlations generated", len(correlations) > 0, f"count={len(correlations)}"))
    if not correlations:
        return False

    corr = correlations[0]
    results.append(_check("confidence >= min threshold", corr.confidence >= 0.35, f"confidence={corr.confidence:.4f}"))

    summary_lower = corr.safe_summary.lower()
    has_forbidden = any(phrase in summary_lower for phrase in FORBIDDEN_PHRASES)
    results.append(_check("safe_summary free of forbidden phrases", not has_forbidden, corr.safe_summary[:80]))
    results.append(_check("operator_review_required=True", corr.operator_review_required is True))
    results.append(_check("review_status=pending", corr.review_status == "pending"))

    results.append(_check("source_pair includes fixed_camera", "fixed_camera" in corr.source_pair))
    results.append(_check("source_pair includes drone_simulation", "drone_simulation" in corr.source_pair))

    obs_a = repo.get_observation(corr.primary_observation_id)
    obs_b = repo.get_observation(corr.matched_observation_id)
    both_have_geo = (
        obs_a is not None
        and obs_b is not None
        and not obs_a.geo_missing
        and not obs_b.geo_missing
        and obs_a.latitude is not None
        and obs_b.latitude is not None
    )
    results.append(_check("map overlay: both observations have geo", both_have_geo))

    breakdown = corr.confidence_breakdown
    results.append(_check("confidence_breakdown present", breakdown is not None))
    results.append(_check("time_score in breakdown", breakdown is not None and breakdown.time_score >= 0))

    health = repo.health_check()
    results.append(_check("health_check returns healthy", health.get("status") == "healthy"))
    results.append(_check("health shows correlations > 0", health.get("correlations", 0) > 0, f"correlations={health.get('correlations')}"))

    timeline = repo.build_fusion_timeline(case_id="case_smoke_001")
    results.append(_check("fusion timeline has entries", len(timeline.entries) > 0, f"entries={len(timeline.entries)}"))

    drone_in_repo = repo.get_observation(drone_obs.observation_id)
    results.append(_check("drone observation simulated=True", drone_in_repo is not None and drone_in_repo.simulated is True))

    return all(results)


def run_live_smoke(device: str = "cpu") -> bool:
    print(f"\n[Live Smoke - device={device}]")
    results = []

    try:
        from app.models.drone_fusion_models import FORBIDDEN_PHRASES, FusionObservation, FusionSourceRef
        from app.repositories.drone_fusion_repository import DroneFusionRepository
        from app.services.drone.drone_simulation_service import DroneSimulationService
        from app.services.drone_fusion.fusion_service import CrossSourceFusionService

        service = DroneSimulationService()
        status = service.connect()
        results.append(_check("AirSim connection", status.connected, status.last_error or "connected"))
        if not status.connected:
            return False

        telemetry = service.get_telemetry()
        frame = service.get_frame()
        results.append(_check("live telemetry available", telemetry.status == "connected", telemetry.last_error or "connected"))
        results.append(_check("live frame available", frame.frame_available, frame.last_error or "frame captured"))
        if telemetry.status != "connected" or not frame.frame_available:
            service.disconnect()
            return False

        lat = telemetry.latitude
        lon = telemetry.longitude
        geo_ok = lat is not None and lon is not None
        results.append(_check("live telemetry includes geo", geo_ok))
        if not geo_ok:
            service.disconnect()
            return False

        class _DummyUser:
            username = "smoke_test"
            role = "admin"
            user_id = "smoke_user"

        ts = frame.timestamp or telemetry.timestamp or _now_iso()
        lat = float(lat)
        lon = float(lon)

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = DroneFusionRepository(root_dir=tmpdir)
            svc = CrossSourceFusionService(repo)

            fixed_cam_obs = FusionObservation(
                source_type="fixed_camera",
                source_id="cam_live_anchor",
                event_id="evt_live_fixed_001",
                case_id="case_live_001",
                timestamp=ts,
                latitude=lat + 0.00001,
                longitude=lon + 0.00001,
                geo_missing=False,
                event_type="drone_detection",
                severity="medium",
                simulated=False,
                evidence_refs=["evt_live_fixed_001"],
                source_ref=FusionSourceRef(
                    source_type="fixed_camera",
                    source_id="cam_live_anchor",
                    event_id="evt_live_fixed_001",
                    simulated=False,
                ),
            )

            drone_obs = FusionObservation(
                source_type="drone_simulation",
                source_id=telemetry.drone_id,
                event_id=f"evt_live_drone_{frame.frame_index}",
                case_id="case_live_001",
                timestamp=ts,
                latitude=lat,
                longitude=lon,
                altitude_meters=telemetry.altitude_meters,
                geo_missing=False,
                event_type="drone_detection",
                severity="medium",
                simulated=True,
                evidence_refs=[f"frame_{frame.frame_index}"],
                source_ref=FusionSourceRef(
                    source_type="drone_simulation",
                    source_id=telemetry.drone_id,
                    event_id=f"evt_live_drone_{frame.frame_index}",
                    simulated=True,
                ),
                metadata={
                    "camera_name": telemetry.camera_name,
                    "frame_index": frame.frame_index,
                    "source_type": "drone_simulation",
                    "simulated": True,
                },
            )

            repo.save_observation(fixed_cam_obs)
            repo.save_observation(drone_obs)

            correlations = svc.correlate(
                [fixed_cam_obs, drone_obs],
                user=_DummyUser(),
                case_id="case_live_001",
                event_id="evt_live_fixed_001",
            )
            results.append(_check("live correlations generated", len(correlations) > 0, f"count={len(correlations)}"))
            if correlations:
                corr = correlations[0]
                results.append(_check("live confidence >= threshold", corr.confidence >= 0.35, f"confidence={corr.confidence:.4f}"))
                summary_lower = corr.safe_summary.lower()
                has_forbidden = any(phrase in summary_lower for phrase in FORBIDDEN_PHRASES)
                results.append(_check("live safe wording enforced", not has_forbidden, corr.safe_summary[:80]))
                results.append(_check("live source_pair includes drone_simulation", "drone_simulation" in corr.source_pair))
                results.append(_check("live source_pair includes fixed_camera", "fixed_camera" in corr.source_pair))
                results.append(_check("live review status pending", corr.review_status == "pending"))
                results.append(_check("live correlation requires review", corr.operator_review_required is True))

        service.disconnect()
    except Exception as exc:
        results.append(_check("live fusion smoke", False, str(exc)[:120]))

    return all(results) if results else True


def main() -> None:
    parser = argparse.ArgumentParser(description="Drone + Fixed Camera Fusion Smoke Test")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    ok = run_deterministic_smoke()
    if args.live:
        ok = run_live_smoke(args.device) and ok

    print()
    if ok:
        print("[PASS] Fusion smoke test complete.")
        sys.exit(0)
    print("[FAIL] Fusion smoke test failed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
