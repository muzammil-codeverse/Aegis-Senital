#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _resolve_npm() -> str:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    return npm or "npm.cmd"


def _run(command: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate city drone FYP local demo readiness.")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--with-e2e", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, object]] = []

    def run_check(name: str, command: list[str], cwd: Path | None = None) -> None:
        code, output = _run(command, cwd=cwd)
        checks.append(
            {
                "name": name,
                "command": " ".join(command),
                "returncode": code,
                "ok": code == 0,
                "output_tail": "\n".join(output.splitlines()[-12:]),
            }
        )

    run_check("validate_runtime_development", [sys.executable, "scripts/validate_runtime.py", "--profile", "development"])
    run_check("runtime_inventory_verify", [sys.executable, "scripts/verify_drone_runtime_inventory.py", "--require-city"])
    run_check("multicamera_capture_smoke", [sys.executable, "scripts/smoke_drone_multicamera_capture.py", "--require-cameras", "front_center,front_left,front_right,downward,rear"])
    run_check("drone_model_smoke", [sys.executable, "scripts/smoke_drone_simulation_pipeline.py", "--strict", "--device", args.device])
    run_check("city_runtime_smoke", [sys.executable, "scripts/smoke_city_drone_runtime.py", "--strict", "--require-city", "--prefer", args.prefer])
    run_check(
        "city_mission_demo_smoke",
        [sys.executable, "scripts/run_city_drone_mission_demo.py", "--mission", "fixed_camera_handoff_demo", "--device", args.device],
    )
    run_check("drone_stream_to_dashboard_smoke", [sys.executable, "scripts/smoke_drone_stream_to_dashboard.py", "--duration", "15", "--device", args.device])
    run_check("drone_fusion_smoke", [sys.executable, "scripts/smoke_drone_fixed_camera_fusion.py"])
    run_check("drone_investigation_path_smoke", [sys.executable, "scripts/smoke_drone_investigation_path.py"])
    run_check("drone_case_evidence_smoke", [sys.executable, "scripts/smoke_drone_case_evidence.py"])
    run_check("drone_analytics_smoke", [sys.executable, "scripts/smoke_drone_analytics.py"])
    run_check("seeded_data_check", [sys.executable, "scripts/seed_city_drone_demo.py", "--city", "multan"])
    run_check("final_demo_data_check", [sys.executable, "scripts/check_final_demo_dashboard_data.py"])
    run_check("running_app_verify", [sys.executable, "scripts/verify_running_demo_app.py", "--with-drone"])
    run_check("frontend_build", [_resolve_npm(), "run", "build"], cwd=ROOT / "frontend")
    if args.with_e2e:
        run_check("frontend_e2e_city_drone", [_resolve_npm(), "run", "e2e", "--", "city-drone-demo.spec.js"], cwd=ROOT / "frontend")

    success = all(bool(item["ok"]) for item in checks)
    print(json.dumps({"status": "ok" if success else "failed", "checks": checks}, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
