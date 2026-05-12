#!/usr/bin/env python3
"""Smoke test: investigative path reconstruction pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

import json
from datetime import datetime, timezone

from app.models.gis_models import CameraGeoProfile, EventGeoMarker
from app.models.investigation_models import PathReconstructionRequest
from app.models.security_models import UserAccount, UserStatus
from app.repositories.gis_repository import get_gis_repository
from app.repositories.investigation_repository import get_investigation_repository
from app.services.path_reconstruction_service import reconstruct_path


def _demo_user() -> UserAccount:
    return UserAccount(
        user_id="smoke_user",
        username="smoke_analyst",
        display_name="Smoke Analyst",
        role="admin",
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def _ensure_demo_cameras(repo) -> None:
    demo_cameras = [
        CameraGeoProfile(camera_id="cam_01", name="Main Gate", latitude=30.1575, longitude=71.5249),
        CameraGeoProfile(camera_id="cam_02", name="North Block", latitude=30.1580, longitude=71.5255),
        CameraGeoProfile(camera_id="cam_03", name="East Wing", latitude=30.1570, longitude=71.5260),
    ]
    for cam in demo_cameras:
        existing = repo.get_camera_geo_profile(cam.camera_id)
        if existing is None:
            repo.upsert_camera_geo_profile(cam)
            print(f"  Seeded camera: {cam.camera_id}")
        else:
            print(f"  Camera exists: {cam.camera_id}")


def main() -> None:
    print("=== Smoke: Investigative Path Reconstruction ===")
    user = _demo_user()

    gis_repo = get_gis_repository()
    inv_repo = get_investigation_repository()

    print("\n[1] Seeding demo GIS cameras...")
    _ensure_demo_cameras(gis_repo)

    print("\n[2] Checking camera graph...")
    from app.services.camera_graph_service import build_camera_graph
    nodes, edges = build_camera_graph(gis_repo, user)
    print(f"  Nodes: {len(nodes)}, Edges: {len(edges)}")
    if not nodes:
        raise SystemExit("FAIL: camera graph is empty after seeding demo GIS profiles")

    print("\n[3] Running path reconstruction...")
    req = PathReconstructionRequest(
        case_id="smoke_case_001",
        event_id="smoke_evt_001",
        backward_minutes=20,
        forward_minutes=30,
    )
    resp = reconstruct_path(req, gis_repo, inv_repo, user)
    print(f"  Status: {resp.status}")
    print(f"  Hypotheses: {len(resp.hypotheses)}")
    print(f"  Evidence refs: {resp.evidence_ref_count}")
    print(f"  Message: {resp.message}")

    for hyp in resp.hypotheses:
        print(f"\n  Hypothesis: {hyp.hypothesis_id}")
        print(f"  Confidence: {hyp.confidence}")
        print(f"  Review status: {hyp.review_status}")
        print(f"  Safe summary: {hyp.safe_summary}")
        print(f"  Evidence refs: {hyp.evidence_refs}")
        print(f"  Steps: {len(hyp.steps)}")
        assert hyp.operator_review_required, "FAIL: operator_review_required must be True"
        assert hyp.review_status == "pending", "FAIL: initial review_status must be pending"
        for forbidden in ("criminal confirmed", "suspect confirmed", "identity confirmed", "guilty"):
            assert forbidden not in hyp.safe_summary.lower(), f"FAIL: forbidden phrase '{forbidden}' in summary"

    print("\n[4] Checking investigation repository health...")
    health = inv_repo.health_check()
    print(f"  Status: {health['status']}")
    print(f"  Stored hypotheses: {health['stored_hypotheses']}")
    assert health["status"] == "healthy", f"FAIL: investigation repo unhealthy: {health}"

    print("\n=== Smoke PASSED ===")


if __name__ == "__main__":
    main()
