#!/usr/bin/env python3
"""Phase 46 — Drone + Fixed Camera Fusion Smoke Test (Task 19).

Deterministic smoke: seeds demo observations, runs fusion correlation,
verifies confidence > threshold, verifies safe wording, verifies map
overlay contract.

Usage:
  python scripts/smoke_drone_fixed_camera_fusion.py
  python scripts/smoke_drone_fixed_camera_fusion.py --live --device cuda
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _check(name: str, ok: bool, detail: str = "", required: bool = True) -> bool:
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_deterministic_smoke() -> bool:
    print("[Deterministic Fusion Smoke]")
    results = []

    # ------------------------------------------------------------------
    # 1. Import models and repository
    # ------------------------------------------------------------------
    try:
        from app.models.drone_fusion_models import (
            FusionObservation, FusionSourceRef, FORBIDDEN_PHRASES
        )
        from app.repositories.drone_fusion_repository import DroneFusionRepository
        from app.services.drone_fusion.fusion_service import CrossSourceFusionService
        results.append(_check("imports OK", True))
    except Exception as exc:
        results.append(_check("imports OK", False, str(exc)))
        return False

    # ------------------------------------------------------------------
    # 2. Seed observations
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 3. Run fusion correlation
    # ------------------------------------------------------------------
    class _DummyUser:
        username = "smoke_test"
        role = "admin"
        user_id = "smoke_user"

    user = _DummyUser()

    svc = CrossSourceFusionService(repo)
    correlations = svc.correlate([fixed_cam_obs, drone_obs], user=user,
                                  case_id="case_smoke_001", event_id="evt_smoke_001")

    results.append(_check("correlations generated", len(correlations) > 0,
                           f"count={len(correlations)}"))

    if not correlations:
        return False

    corr = correlations[0]
    results.append(_check("confidence >= min threshold", corr.confidence >= 0.35,
                           f"confidence={corr.confidence:.4f}"))

    # ------------------------------------------------------------------
    # 4. Verify safe wording
    # ------------------------------------------------------------------
    summary_lower = corr.safe_summary.lower()
    has_forbidden = any(phrase in summary_lower for phrase in FORBIDDEN_PHRASES)
    results.append(_check("safe_summary free of forbidden phrases", not has_forbidden,
                           corr.safe_summary[:80]))
    results.append(_check("operator_review_required=True", corr.operator_review_required is True))
    results.append(_check("review_status=pending", corr.review_status == "pending"))

    # ------------------------------------------------------------------
    # 5. Verify source pair
    # ------------------------------------------------------------------
    has_fixed = "fixed_camera" in corr.source_pair
    has_drone = "drone_simulation" in corr.source_pair
    results.append(_check("source_pair includes fixed_camera", has_fixed))
    results.append(_check("source_pair includes drone_simulation", has_drone))

    # ------------------------------------------------------------------
    # 6. Verify map overlay contract
    # ------------------------------------------------------------------
    obs_a = repo.get_observation(corr.primary_observation_id)
    obs_b = repo.get_observation(corr.matched_observation_id)
    both_have_geo = (
        obs_a and not obs_a.geo_missing and obs_a.latitude is not None and
        obs_b and not obs_b.geo_missing and obs_b.latitude is not None
    )
    results.append(_check("map overlay: both observations have geo", both_have_geo))

    # ------------------------------------------------------------------
    # 7. Verify confidence breakdown
    # ------------------------------------------------------------------
    bd = corr.confidence_breakdown
    results.append(_check("confidence_breakdown present", bd is not None))
    results.append(_check("time_score in breakdown", bd is not None and bd.time_score >= 0))

    # ------------------------------------------------------------------
    # 8. Health check
    # ------------------------------------------------------------------
    health = repo.health_check()
    results.append(_check("health_check returns healthy", health.get("status") == "healthy"))
    results.append(_check("health shows correlations > 0", health.get("correlations", 0) > 0,
                           f"correlations={health.get('correlations')}"))

    # ------------------------------------------------------------------
    # 9. Timeline
    # ------------------------------------------------------------------
    timeline = repo.build_fusion_timeline(case_id="case_smoke_001")
    results.append(_check("fusion timeline has entries", len(timeline.entries) > 0,
                           f"entries={len(timeline.entries)}"))

    # ------------------------------------------------------------------
    # 10. Drone observation is simulated
    # ------------------------------------------------------------------
    drone_in_repo = repo.get_observation(drone_obs.observation_id)
    results.append(_check("drone observation simulated=True", drone_in_repo and drone_in_repo.simulated is True))

    return all(results)


def run_live_smoke(device: str = "cpu") -> bool:
    print(f"\n[Live Smoke — device={device}]")
    results = []
    try:
        from scripts.smoke_drone_simulation_pipeline import main as pipeline_main
        results.append(_check("drone simulation pipeline import OK", True))
    except ImportError as exc:
        results.append(_check("drone simulation pipeline import", False, str(exc), required=False))

    try:
        from app.services.drone.cosys_airsim_client import CosysAirSimClient
        client = CosysAirSimClient()
        client.connect()
        results.append(_check("AirSim connection", True))
    except Exception as exc:
        results.append(_check("AirSim connection", False, str(exc)[:80], required=False))

    return all(r for r in results) if results else True


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 46 Fusion Smoke Test")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    ok = run_deterministic_smoke()

    if args.live:
        ok_live = run_live_smoke(args.device)
        ok = ok and ok_live

    print()
    if ok:
        print("[PASS] Fusion smoke test complete.")
        sys.exit(0)
    else:
        print("[FAIL] Fusion smoke test failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
