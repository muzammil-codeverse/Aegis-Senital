from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from scripts.drone_runtime_catalog import (
        DEFAULT_HOST,
        DEFAULT_INVENTORY_PATH,
        DEFAULT_PORT,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        is_port_open,
        latest_crash_summary,
        persist_inventory,
        select_runtime,
    )
except ModuleNotFoundError:
    from drone_runtime_catalog import (  # type: ignore[no-redef]
        DEFAULT_HOST,
        DEFAULT_INVENTORY_PATH,
        DEFAULT_PORT,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        is_port_open,
        latest_crash_summary,
        persist_inventory,
        select_runtime,
    )


def _build_launch_args(windowed: bool, res: str) -> list[str]:
    args: list[str] = []
    if windowed:
        args.append("-windowed")
    if "x" in res.lower():
        try:
            w, h = res.lower().split("x", 1)
            args.extend([f"-ResX={int(w)}", f"-ResY={int(h)}"])
        except Exception:
            pass
    return args


def _launch(executable: Path, args: list[str]) -> subprocess.Popen[bytes]:
    if executable.suffix.lower() == ".bat":
        command = ["cmd.exe", "/c", str(executable), *args]
    else:
        command = [str(executable), *args]
    return subprocess.Popen(
        command,
        cwd=str(executable.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def _wait_for_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(1.0)
    return False


def _kill_stale_processes(runtime_root: Path) -> list[dict[str, Any]]:
    killed: list[dict[str, Any]] = []
    try:
        import psutil  # type: ignore
    except Exception:
        return killed

    allowed_roots = {str(runtime_root).lower()}
    env_root = os.environ.get("AEGIS_DRONE_SIM_ENV_ROOT")
    if env_root:
        allowed_roots.add(str(Path(env_root)).lower())

    for proc in psutil.process_iter(attrs=["pid", "name", "exe", "cmdline"]):
        try:
            info = proc.info
            name = str(info.get("name") or "").lower()
            exe = str(info.get("exe") or "")
            cmdline = " ".join(info.get("cmdline") or [])
            fingerprint = f"{name} {exe} {cmdline}".lower()
            if not any(tag in fingerprint for tag in ("airsim", "blocks", "cityenviron", "neighborhood", "run.bat")):
                continue
            normalized_exe = exe.lower()
            if normalized_exe and not any(normalized_exe.startswith(root) for root in allowed_roots):
                continue
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except Exception:
                proc.kill()
            killed.append({"pid": info.get("pid"), "name": info.get("name"), "exe": exe})
        except Exception:
            continue
    return killed


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch city/neighborhood AirSim runtime with explicit fallback handling.")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--fallback", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--res", default="960x540")
    parser.add_argument("--kill-stale", action="store_true")
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()

    selection = select_runtime(prefer=args.prefer, fallback=args.fallback, runtime_root=runtime_root)
    if not selection.get("available"):
        payload = {
            "status": "failed",
            "reason": "No runtime installation found",
            "selected_runtime": None,
            "fallback_used": False,
        }
        print(json.dumps(payload, indent=2))
        return 1

    if args.kill_stale:
        killed = _kill_stale_processes(runtime_root)
    else:
        killed = []

    executable = Path(str(selection.get("executable_path")))
    runtime_dir = Path(str(selection.get("runtime_dir")))
    launch_args = _build_launch_args(args.windowed, args.res)

    if is_port_open(args.host, args.port):
        inventory = discover_runtime_inventory(runtime_root)
        inventory["selected_runtime"] = selection.get("name")
        inventory["selected_runtime_details"] = selection
        inventory["launch_status"] = {
            "status": "already_running",
            "fallback_used": bool(selection.get("fallback_used")),
            "killed_stale": killed,
        }
        persist_inventory(inventory, DEFAULT_INVENTORY_PATH)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "selected_runtime": selection.get("name"),
                    "runtime_type": selection.get("runtime_type"),
                    "fallback_used": bool(selection.get("fallback_used")),
                    "already_running": True,
                    "endpoint": f"{args.host}:{args.port}",
                    "killed_stale": killed,
                },
                indent=2,
            )
        )
        return 0

    attempts = [launch_args]
    if "-ResX=640" not in launch_args:
        fallback_args = [item for item in launch_args if not item.startswith("-ResX=") and not item.startswith("-ResY=")]
        fallback_args.extend(["-ResX=640", "-ResY=480"])
        attempts.append(fallback_args)

    port_ready = False
    used_args = launch_args
    for attempt_args in attempts:
        used_args = attempt_args
        _launch(executable, attempt_args)
        if _wait_for_port(args.host, args.port, args.timeout):
            port_ready = True
            break
    if not port_ready:
        crash = latest_crash_summary(runtime_dir)
        payload = {
            "status": "failed",
            "selected_runtime": selection.get("name"),
            "runtime_type": selection.get("runtime_type"),
            "fallback_used": bool(selection.get("fallback_used")),
            "endpoint": f"{args.host}:{args.port}",
            "crash_summary": crash,
            "killed_stale": killed,
        }
        print(json.dumps(payload, indent=2))
        return 2

    inventory = discover_runtime_inventory(runtime_root)
    inventory["selected_runtime"] = selection.get("name")
    inventory["selected_runtime_details"] = selection
    inventory["launch_status"] = {
        "status": "running",
        "fallback_used": bool(selection.get("fallback_used")),
        "windowed": bool(args.windowed),
        "resolution": args.res,
        "killed_stale": killed,
    }
    persist_inventory(inventory, DEFAULT_INVENTORY_PATH)

    print(
        json.dumps(
            {
                "status": "ok",
                "selected_runtime": selection.get("name"),
                "runtime_type": selection.get("runtime_type"),
                "fallback_used": bool(selection.get("fallback_used")),
                "endpoint": f"{args.host}:{args.port}",
                "launch_args": used_args,
                "killed_stale": killed,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
