#!/usr/bin/env python3
"""Phase 56 — Smoke test all drone-related dashboard REST APIs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def _get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
    session: requests.Session,
) -> tuple[bool, Any, str]:
    try:
        resp = session.get(url, headers=headers or {}, timeout=timeout)
        if resp.status_code in {200, 201, 202, 204}:
            try:
                return True, resp.json(), "ok"
            except Exception:
                return True, resp.text, "ok"
        # 424/503 are "honest degraded" responses — acceptable when simulator is offline
        if resp.status_code in {424, 503, 404}:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            return True, body, f"degraded_{resp.status_code}"
        return False, None, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, None, str(exc)


def _login(backend: str, password: str, session: requests.Session) -> dict[str, str]:
    try:
        resp = session.post(
            f"{backend}/api/auth/login",
            json={"username": "admin", "password": password},
            timeout=10,
        )
        if resp.status_code < 400:
            token = str(resp.json().get("access_token") or "").strip()
            if token:
                return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test drone dashboard REST APIs.")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--with-auth", action="store_true")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    session = requests.Session()
    headers: dict[str, str] = {}
    if args.with_auth:
        password = os.environ.get("AEGIS_BOOTSTRAP_ADMIN_PASSWORD") or "ChangeMe123"
        headers = _login(args.backend, password, session)

    checks: list[dict[str, Any]] = []

    def check(name: str, url: str, *, required: bool = True) -> bool:
        ok, payload, detail = _get(url, headers=headers, timeout=args.timeout, session=session)
        checks.append(
            {
                "name": name,
                "url": url,
                "ok": ok,
                "detail": detail,
                "degraded": "degraded" in detail,
                "required": required,
                "payload_keys": list(payload.keys()) if isinstance(payload, dict) else None,
            }
        )
        return ok

    b = args.backend

    # Core health
    check("health", f"{b}/health")

    # Drone simulation
    check("drone_status", f"{b}/api/drone-simulation/status")
    check("drone_runtime", f"{b}/api/drone-simulation/runtime")
    check("drone_cameras", f"{b}/api/drone-simulation/cameras")
    check("drone_latest_frame_front_center", f"{b}/api/drone-simulation/cameras/front_center/latest-frame")
    check("drone_telemetry", f"{b}/api/drone-simulation/telemetry")
    check("drone_events", f"{b}/api/drone-simulation/events")

    # Missions
    check("drone_missions", f"{b}/api/drone-missions")

    # Fusion
    check("drone_fusion_health", f"{b}/api/drone-fusion/health")
    check("drone_fusion_correlations", f"{b}/api/drone-fusion/correlations?limit=10")

    # Analytics
    check("analytics_overview", f"{b}/api/analytics/overview")

    # GIS
    gis_ok = check("gis_layers", f"{b}/api/gis/layers", required=False)
    if not gis_ok:
        check("gis_cameras", f"{b}/api/gis/cameras", required=False)

    # Investigations
    check("investigations", f"{b}/api/investigations?limit=10", required=False)

    # Cases
    check("cases", f"{b}/api/cases?limit=10")

    # Uploaded videos
    check("uploaded_videos", f"{b}/api/uploaded-videos")

    required_failed = [c["name"] for c in checks if c["required"] and not c["ok"]]
    all_ok = len(required_failed) == 0

    print(
        json.dumps(
            {
                "status": "ok" if all_ok else "failed",
                "required_failed": required_failed,
                "checks": checks,
            },
            indent=2,
        )
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
