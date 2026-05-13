#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESS_DIR = ROOT / "storage" / "demo_runtime"


def _resolve_npm() -> str:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    return npm or "npm.cmd"


def _verify_cuda() -> tuple[bool, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
        return False, "CUDA unavailable"
    except Exception as exc:
        return False, str(exc)


def _run_script(script: str, *args: str) -> tuple[int, str]:
    command = [sys.executable, script, *args]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout


def _start_process(command: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch full local city drone demo stack.")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--with-drone", action="store_true")
    parser.add_argument("--city", default="multan")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", default="8000")
    parser.add_argument("--frontend-port", default="5173")
    args = parser.parse_args()

    PROCESS_DIR.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "python": sys.executable,
        "project_root": str(ROOT),
        "venv_active": ".venv" in str(Path(sys.executable)).lower(),
    }

    cuda_ok, cuda_name = _verify_cuda()
    payload["cuda_available"] = cuda_ok
    payload["cuda_device"] = cuda_name

    steps: list[dict[str, object]] = []

    def run_step(name: str, script: str, *step_args: str) -> None:
        code, output = _run_script(script, *step_args)
        steps.append(
            {
                "name": name,
                "script": script,
                "args": list(step_args),
                "returncode": code,
                "output_tail": "\n".join(output.splitlines()[-12:]),
            }
        )

    run_step("configure_multicamera", "scripts/configure_drone_multicamera_settings.py", "--profile", "city_demo")
    if args.with_drone:
        run_step(
            "launch_runtime",
            "scripts/launch_city_drone_runtime.py",
            "--prefer",
            args.prefer,
            "--windowed",
            "--res",
            "960x540",
        )
    run_step("seed_demo_data", "scripts/seed_city_drone_demo.py", "--reset-demo-only", "--city", args.city)

    backend_process = _start_process(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--app-dir",
            "backend",
            "--host",
            args.backend_host,
            "--port",
            str(args.backend_port),
        ],
        ROOT,
    )
    frontend_process = _start_process(
        [_resolve_npm(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.frontend_port)],
        ROOT / "frontend",
    )

    time.sleep(3)

    route_checklist = [
        "Dashboard",
        "Drone Operations Hub",
        "Drone Simulation",
        "Drone Mission Planner",
        "Drone Fusion",
        "Map Operations",
        "Investigation",
        "Cases",
        "Uploaded Video",
        "Analytics",
    ]

    payload.update(
        {
            "steps": steps,
            "backend": {
                "host": args.backend_host,
                "port": int(args.backend_port),
                "pid": backend_process.pid,
            },
            "frontend": {
                "host": "127.0.0.1",
                "port": int(args.frontend_port),
                "pid": frontend_process.pid,
            },
            "route_checklist": route_checklist,
            "with_drone": bool(args.with_drone),
        }
    )

    process_file = PROCESS_DIR / "phase55_demo_processes.json"
    process_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["process_file"] = str(process_file.resolve())

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
