from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests


def _get(url: str, headers: dict[str, str] | None = None, timeout: int = 10, session: requests.Session | None = None) -> tuple[bool, Any, str]:
    client = session or requests
    try:
        resp = client.get(url, headers=headers or {}, timeout=timeout)
        if resp.status_code >= 400:
            return False, None, f"HTTP {resp.status_code}"
        try:
            return True, resp.json(), "ok"
        except Exception:
            return True, resp.text, "ok"
    except Exception as exc:
        return False, None, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify running local demo backend/frontend and key APIs.")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend", default="http://127.0.0.1:5173")
    parser.add_argument("--with-drone", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    headers: dict[str, str] = {}
    bootstrap_password = os.environ.get("AEGIS_BOOTSTRAP_ADMIN_PASSWORD") or "ChangeMe123"
    try:
        login_resp = session.post(
            f"{args.backend}/api/auth/login",
            json={"username": "admin", "password": bootstrap_password},
            timeout=10,
        )
        if login_resp.status_code < 400:
            login_payload = login_resp.json()
            access_token = str(login_payload.get("access_token") or "").strip()
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
    except Exception:
        pass

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "ok") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    ok, _, detail = _get(f"{args.backend}/openapi.json", session=session)
    check("backend_reachable", ok, detail)

    ok, _, detail = _get(f"{args.frontend}/", session=session)
    check("frontend_reachable", ok, detail)

    if args.with_drone:
        ok, payload, detail = _get(f"{args.backend}/api/drone-simulation/status", headers=headers, session=session)
        check("drone_status_api", ok, detail)

        ok_rt, _, detail_rt = _get(f"{args.backend}/api/drone-simulation/runtime", headers=headers, session=session)
        check("drone_runtime_api", ok_rt, detail_rt)

        ok_cam, cams_payload, detail_cam = _get(f"{args.backend}/api/drone-simulation/cameras", headers=headers, session=session)
        check("drone_cameras_api", ok_cam, detail_cam)

        camera_name = "front_center"
        if ok_cam and isinstance(cams_payload, dict) and cams_payload.get("items"):
            camera_name = str((cams_payload.get("items") or [{}])[0].get("camera_name") or "front_center")

        ok_frame, frame_payload, detail_frame = _get(
            f"{args.backend}/api/drone-simulation/cameras/{camera_name}/latest-frame",
            headers=headers,
            session=session,
        )
        frame_honest = False
        if ok_frame and isinstance(frame_payload, dict):
            item = frame_payload.get("item") or {}
            frame_honest = bool(item.get("frame_available")) or str(item.get("status")) in {"disconnected", "degraded", "connected"}
        check("drone_latest_frame_api", ok_frame and frame_honest, detail_frame)

        ok_tel, _, detail_tel = _get(f"{args.backend}/api/drone-simulation/telemetry", headers=headers, session=session)
        check("drone_telemetry_api", ok_tel, detail_tel)

    ok_gis, gis_payload, detail_gis = _get(f"{args.backend}/api/gis/layers", headers=headers, session=session)
    gis_has_data = bool(isinstance(gis_payload, dict) and (gis_payload.get("item") or gis_payload.get("items") is not None))
    check("gis_route_data", ok_gis and gis_has_data, detail_gis)

    ok_fusion, fusion_payload, detail_fusion = _get(
        f"{args.backend}/api/drone-fusion/correlations?limit=10",
        headers=headers,
        session=session,
    )
    fusion_exists = bool(ok_fusion and isinstance(fusion_payload, dict) and (fusion_payload.get("count", 0) >= 0))
    check("fusion_api", fusion_exists, detail_fusion)

    ok_cases, cases_payload, detail_cases = _get(f"{args.backend}/api/cases?limit=10", headers=headers, session=session)
    case_exists = bool(ok_cases and isinstance(cases_payload, dict) and cases_payload.get("count", 0) >= 0)
    check("case_api", case_exists, detail_cases)

    ok_uv, _, detail_uv = _get(f"{args.backend}/api/uploaded-videos", headers=headers, session=session)
    check("uploaded_video_api", ok_uv, detail_uv)

    ok_analytics, _, detail_analytics = _get(f"{args.backend}/api/analytics/overview", headers=headers, session=session)
    check("analytics_api", ok_analytics, detail_analytics)

    all_ok = all(item["ok"] for item in checks)
    print(json.dumps({"status": "ok" if all_ok else "failed", "checks": checks}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
