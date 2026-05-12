#!/usr/bin/env python3
"""Backend API smoke for final demo readiness."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient

from app.models.gis_models import CameraGeoProfile
from app.models.security_models import UserAccount, UserStatus
from app.repositories.gis_repository import get_gis_repository
from app.services import auth_service as auth_module
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from main import app


def _print(status: str, name: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


def _user(role: str, metadata: dict[str, Any] | None = None) -> UserAccount:
    return UserAccount(
        user_id=f"phase50-{role}",
        username=role,
        display_name=role.title(),
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
        metadata=metadata or {},
    )


def _seed_demo_gis_profiles() -> None:
    repo = get_gis_repository()
    profiles = [
        CameraGeoProfile(
            camera_id="demo_cam_01",
            name="Demo perimeter camera 01",
            latitude=30.1585,
            longitude=71.5259,
            heading_degrees=45.0,
            fov_degrees=75.0,
            coverage_radius_meters=80.0,
            region="demo_zone",
            metadata={"seed": "phase50", "source_type": "live_stream"},
        ),
        CameraGeoProfile(
            camera_id="demo_cam_02",
            name="Demo perimeter camera 02",
            latitude=30.1563,
            longitude=71.5241,
            heading_degrees=200.0,
            fov_degrees=75.0,
            coverage_radius_meters=90.0,
            region="demo_zone",
            metadata={"seed": "phase50", "source_type": "live_stream"},
        ),
        CameraGeoProfile(
            camera_id="cam_01",
            name="Main Gate",
            latitude=30.1575,
            longitude=71.5249,
            metadata={"seed": "phase50", "source_type": "live_stream"},
        ),
        CameraGeoProfile(
            camera_id="cam_02",
            name="North Block",
            latitude=30.1580,
            longitude=71.5255,
            metadata={"seed": "phase50", "source_type": "live_stream"},
        ),
        CameraGeoProfile(
            camera_id="cam_03",
            name="East Wing",
            latitude=30.1570,
            longitude=71.5260,
            metadata={"seed": "phase50", "source_type": "live_stream"},
        ),
    ]
    for profile in profiles:
        repo.upsert_camera_geo_profile(profile)


def _response_status(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("status", "ready"):
            if key in data:
                return str(data.get(key))
    return None


def _response_detail(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data)[:200]
    if "detail" in data and data["detail"]:
        return str(data["detail"])[:200]
    if "status" in data:
        return f"status={data['status']}"
    if "ready" in data:
        return f"ready={data['ready']}"
    if "count" in data:
        return f"count={data['count']}"
    return "ok"


def _run_request(client: TestClient, method: str, path: str, token: str | None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if method == "GET":
        response = client.get(path, headers=headers)
    else:
        response = client.post(path, headers=headers, json=body)
    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    return response.status_code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test backend runtime endpoints.")
    parser.add_argument("--json-out", default="", help="Optional JSON output path")
    args = parser.parse_args()

    _seed_demo_gis_profiles()
    drone_id = get_drone_simulation_service().drone_id
    auth_service = auth_module.get_auth_service()
    original_auth = auth_service.get_current_user_from_token

    users = {
        "viewer": _user("viewer", metadata={"camera_scopes": ["cam_01", drone_id]}),
        "operator": _user("operator", metadata={"camera_scopes": ["cam_01", drone_id]}),
        "supervisor": _user("supervisor", metadata={"camera_scopes": ["cam_01", drone_id]}),
        "admin": _user("admin"),
    }
    auth_service.get_current_user_from_token = lambda token: users.get(token)

    checks: list[dict[str, Any]] = []
    started = time.time()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            security_checks = [
                ("auth_required_system_health", "GET", "/api/system/health", None, None, 401),
                ("rbac_enforced_model_governance", "POST", "/api/model-governance/validate", "viewer", {"profile": "development"}, 403),
            ]
            for name, method, path, token, body, expected in security_checks:
                code, payload = _run_request(client, method, path, token, body)
                passed = code == expected
                detail = f"http={code} expected={expected}"
                checks.append(
                    {
                        "name": name,
                        "status": "passed" if passed else "failed",
                        "required": True,
                        "http_status": code,
                        "expected_status": expected,
                        "detail": detail,
                        "payload_status": _response_status(payload),
                    }
                )
                _print("PASS" if passed else "FAIL", name, detail)

            endpoint_checks = [
                ("system_health", "GET", "/api/system/health", "admin", None, 200),
                ("system_readiness", "GET", "/api/system/readiness", "admin", None, 200),
                ("cameras", "GET", "/api/cameras", "viewer", None, 200),
                ("alerts", "GET", "/api/alerts", "viewer", None, 200),
                ("gis_config", "GET", "/api/gis/config", "viewer", None, 200),
                ("investigation_camera_graph", "GET", "/api/investigation/cameras/graph", "admin", None, 200),
                ("drone_simulation_status", "GET", "/api/drone-simulation/status", "admin", None, 200),
                ("drone_missions", "GET", "/api/drone-missions", "admin", None, 200),
                ("drone_fusion_health", "GET", "/api/drone-fusion/health", "admin", None, 200),
                ("analytics_overview", "GET", "/api/analytics/overview", "viewer", None, 200),
                ("model_governance_validate", "POST", "/api/model-governance/validate", "admin", {"profile": "development"}, 200),
                ("cases", "GET", "/api/cases", "viewer", None, 200),
                ("uploaded_videos", "GET", "/api/uploaded-videos", "supervisor", None, 200),
                ("llm_status", "GET", "/api/llm/status", "viewer", None, 200),
            ]

            for name, method, path, token, body, expected in endpoint_checks:
                code, payload = _run_request(client, method, path, token, body)
                passed = code == expected
                detail = _response_detail(payload)
                payload_status = _response_status(payload)
                if name == "investigation_camera_graph" and passed and isinstance(payload, dict):
                    node_count = int((((payload.get("item") or {}).get("node_count")) or 0))
                    passed = node_count >= 2
                    detail = f"node_count={node_count}"
                checks.append(
                    {
                        "name": name,
                        "status": "passed" if passed else "failed",
                        "required": True,
                        "http_status": code,
                        "expected_status": expected,
                        "detail": detail,
                        "payload_status": payload_status,
                    }
                )
                _print("PASS" if passed else "FAIL", name, f"http={code} {detail}")
    finally:
        auth_service.get_current_user_from_token = original_auth

    failures = [item["name"] for item in checks if item["status"] == "failed"]
    summary = {
        "generated_at": started,
        "overall_status": "failed" if failures else "passed",
        "failures": failures,
        "checks": checks,
    }

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print()
    _print("FAIL" if failures else "PASS", "overall", summary["overall_status"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
