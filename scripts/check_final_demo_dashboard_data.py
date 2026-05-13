from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.repositories.drone_fusion_repository import get_drone_fusion_repository
from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.repositories.gis_repository import get_gis_repository
from app.models.security_models import UserAccount
from app.services.case_service import get_case_service


def _user() -> UserAccount:
    import time

    now = time.time()
    return UserAccount(
        user_id="phase55_user",
        username="phase55_user",
        display_name="Phase55 User",
        role="admin",
        status="active",
        password_hash="x",
        created_at=now,
        updated_at=now,
    )


def main() -> int:
    gis_repo = get_gis_repository()
    case_service = get_case_service()
    mission_repo = get_drone_mission_repository()
    fusion_repo = get_drone_fusion_repository()

    cameras = [item for item in gis_repo.list_camera_geo_profiles(_user()) if bool((item.metadata or {}).get("demo"))]
    cases = [item for item in case_service.list_cases({"limit": 2000}) if bool((item.metadata or {}).get("demo"))]
    missions = [item for item in mission_repo.list_missions(limit=2000) if bool((item.metadata or {}).get("demo"))]
    fusion_obs = [item for item in fusion_repo.list_observations(limit=2000) if bool((item.metadata or {}).get("demo"))]

    payload = {
        "status": "ok",
        "demo_cameras": len(cameras),
        "demo_cases": len(cases),
        "demo_missions": len(missions),
        "demo_fusion_candidates": len(fusion_obs),
        "analytics_readable": True,
    }

    checks = {
        "demo_cameras>=5": len(cameras) >= 5,
        "demo_case_exists": len(cases) >= 1,
        "drone_mission_exists": len(missions) >= 1,
        "fusion_candidate_exists": len(fusion_obs) >= 1,
    }
    payload["checks"] = checks

    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        payload["status"] = "failed"
        payload["failed_checks"] = failed

    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
