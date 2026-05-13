#!/usr/bin/env python3
"""
repair_blocks_runtime.py — Detect, stabilise, and launch the Cosys-AirSim Blocks runtime.

Phase 56 fix: Blocks.exe previously crashed because Windows routed it to the
Intel UHD integrated GPU instead of the dedicated NVIDIA RTX 4060. This script:
  1. Detects the Blocks executable.
  2. Kills any stale Blocks.exe process safely.
  3. Backs up and rewrites a minimal stable AirSim settings.json.
  4. Launches Blocks in low-res windowed mode with -dx12 (forces NVIDIA on hybrid laptops).
  5. Waits for RPC port 41451 to open.
  6. Optionally runs a telemetry + front_center frame smoke test.
  7. Prints the latest crash summary if the launch fails.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_RUNTIME_DIR = Path(
    os.environ.get("AEGIS_DRONE_SIM_RUNTIME_DIR", r"C:\AegisExternalTools\drone_sim\runtime")
)
DEFAULT_BLOCKS_RELATIVE = Path(
    r"environments\Blocks\Blocks_packaged_Windows_55_33\Windows\Blocks.exe"
)
AIRSIM_SETTINGS_DIR = Path.home() / "Documents" / "AirSim"
AIRSIM_SETTINGS_PATH = AIRSIM_SETTINGS_DIR / "settings.json"
DEFAULT_HOST = os.environ.get("AEGIS_AIRSIM_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AEGIS_AIRSIM_PORT", "41451"))

STABLE_SETTINGS = {
    "SeeDocsAt": "https://github.com/CodexLabsLLC/Colosseum/blob/main/docs/settings.md",
    "SettingsVersion": 1.2,
    "SimMode": "Multirotor",
    "ClockSpeed": 1,
    "ViewMode": "NoDisplay",
    "RpcEnabled": True,
    "EnableCollisionPassthrough": False,
    "Vehicles": {
        "Drone1": {
            "VehicleType": "SimpleFlight",
            "AutoCreate": True,
            "Cameras": {
                "front_center": {
                    "CaptureSettings": [
                        {
                            "ImageType": 0,
                            "Width": 640,
                            "Height": 480,
                            "FOV_Degrees": 90,
                        }
                    ],
                    "NoiseSettings": [{"Enabled": False}],
                    "X": 0.5,
                    "Y": 0.0,
                    "Z": -0.1,
                    "Pitch": 0,
                    "Roll": 0,
                    "Yaw": 0,
                },
                "downward": {
                    "CaptureSettings": [
                        {
                            "ImageType": 0,
                            "Width": 320,
                            "Height": 240,
                            "FOV_Degrees": 90,
                        }
                    ],
                    "NoiseSettings": [{"Enabled": False}],
                    "X": 0.0,
                    "Y": 0.0,
                    "Z": -0.1,
                    "Pitch": -90,
                    "Roll": 0,
                    "Yaw": 0,
                },
            },
        }
    },
}


def _resolve_blocks(runtime_dir: Path) -> Path:
    explicit = runtime_dir / DEFAULT_BLOCKS_RELATIVE
    if explicit.exists():
        return explicit
    matches = sorted(runtime_dir.rglob("Blocks.exe"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"Blocks.exe not found under {runtime_dir}. "
        "Extract the Cosys-AirSim Blocks runtime first."
    )


def _is_port_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _kill_stale_blocks() -> int:
    killed = 0
    if platform.system() != "Windows":
        return killed
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Blocks.exe", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        pids = [
            line.split(",")[1].strip('"')
            for line in result.stdout.splitlines()
            if "Blocks.exe" in line and "," in line
        ]
        for pid in pids:
            subprocess.run(
                ["taskkill", "/PID", pid, "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            killed += 1
    except Exception:
        pass
    return killed


def _backup_settings() -> Path | None:
    if not AIRSIM_SETTINGS_PATH.exists():
        return None
    backup = AIRSIM_SETTINGS_PATH.with_suffix(".json.bak")
    shutil.copy2(AIRSIM_SETTINGS_PATH, backup)
    return backup


def _write_minimal_settings() -> Path:
    AIRSIM_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    AIRSIM_SETTINGS_PATH.write_text(json.dumps(STABLE_SETTINGS, indent=2), encoding="utf-8")
    return AIRSIM_SETTINGS_PATH


def _latest_crash_summary(runtime_dir: Path) -> str | None:
    crash_root = (
        runtime_dir
        / "environments"
        / "Blocks"
        / "Blocks_packaged_Windows_55_33"
        / "Windows"
        / "Blocks"
        / "Saved"
        / "Crashes"
    )
    if not crash_root.exists():
        return None
    entries = [p for p in crash_root.iterdir() if p.is_dir()]
    if not entries:
        return None
    latest = max(entries, key=lambda p: p.stat().st_mtime)
    context = latest / "CrashContext.runtime-xml"
    if not context.exists():
        return f"Latest crash dir: {latest}"
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(context.read_text(encoding="utf-8", errors="replace"))
        def tag(name: str) -> str:
            node = root.find(f".//{name}")
            return (node.text or "unknown").strip() if node is not None else "unknown"
        return (
            f"type={tag('CrashType')} | gpu={tag('Misc.PrimaryGPUBrand')} | "
            f"error={tag('ErrorMessage')[:120]}"
        )
    except Exception:
        return f"Latest crash dir: {latest}"


def _smoke_rpc(host: str, port: int) -> dict[str, object]:
    try:
        try:
            import cosysairsim as airsim
        except ImportError:
            import airsim  # type: ignore[no-redef]
        client = airsim.MultirotorClient(ip=host, port=port)
        client.confirmConnection()
        state = client.getMultirotorState()
        gps = getattr(state, "gps_location", None)
        request = airsim.ImageRequest("front_center", airsim.ImageType.Scene, False, False)
        response = client.simGetImages([request])[0]
        width = int(getattr(response, "width", 0) or 0)
        height = int(getattr(response, "height", 0) or 0)
        return {
            "rpc_ok": True,
            "telemetry_ok": True,
            "frame_ok": width > 0 and height > 0,
            "frame_width": width,
            "frame_height": height,
            "gps": {
                "lat": float(getattr(gps, "latitude", 0.0) or 0.0) if gps else None,
                "lon": float(getattr(gps, "longitude", 0.0) or 0.0) if gps else None,
                "alt": float(getattr(gps, "altitude", 0.0) or 0.0) if gps else None,
            },
        }
    except Exception as exc:
        return {"rpc_ok": False, "telemetry_ok": False, "frame_ok": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair and launch Blocks AirSim runtime.")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait for RPC port")
    parser.add_argument("--launch", action="store_true", help="Launch Blocks.exe")
    parser.add_argument("--kill-stale", action="store_true", help="Kill any running Blocks.exe first")
    parser.add_argument("--write-settings", action="store_true", help="Write stable settings.json")
    parser.add_argument("--verify", action="store_true", help="Run RPC telemetry+frame smoke after launch")
    parser.add_argument("--print-crash-summary", action="store_true")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    result: dict[str, object] = {"runtime_dir": str(runtime_dir)}

    if args.print_crash_summary:
        summary = _latest_crash_summary(runtime_dir)
        print(json.dumps({"crash_summary": summary}, indent=2))

    try:
        executable = _resolve_blocks(runtime_dir)
        result["executable"] = str(executable)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, indent=2))
        return 1

    if args.kill_stale:
        killed = _kill_stale_blocks()
        result["killed_stale"] = killed
        if killed > 0:
            time.sleep(2)

    if args.write_settings:
        backup = _backup_settings()
        settings_path = _write_minimal_settings()
        result["settings_written"] = str(settings_path)
        result["settings_backup"] = str(backup) if backup else None

    if _is_port_open(args.host, args.port):
        result["already_running"] = True
        print(f"[repair_blocks] Runtime already reachable at {args.host}:{args.port}")
    elif args.launch:
        _write_minimal_settings()
        launch_flags = [
            str(executable),
            "-windowed",
            "-ResX=640",
            "-ResY=480",
            "-NoSound",
            "-dx12",
        ]
        print(f"[repair_blocks] Launching: {' '.join(launch_flags)}")
        print("[repair_blocks] NOTE: If Blocks runs on Intel UHD GPU, the simulation may")
        print("  be unstable. Fix: Windows Settings > System > Display > Graphics >")
        print(f"  Add '{executable.name}' > High performance (NVIDIA).")
        try:
            subprocess.Popen(
                launch_flags,
                cwd=str(executable.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        except Exception as exc:
            print(json.dumps({"status": "failed", "reason": f"Launch failed: {exc}"}, indent=2))
            return 1

        print(f"[repair_blocks] Waiting for RPC on {args.host}:{args.port} (timeout={args.timeout}s)…")
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            if _is_port_open(args.host, args.port):
                print(f"[repair_blocks] RPC reachable at {args.host}:{args.port}")
                result["rpc_open"] = True
                break
            time.sleep(1)
        else:
            result["rpc_open"] = False
            crash = _latest_crash_summary(runtime_dir)
            result["crash_summary"] = crash
            if crash:
                print(f"[repair_blocks] Crash detected: {crash}")
            print(json.dumps({"status": "failed", "reason": "RPC port did not open", **result}, indent=2))
            return 2
    else:
        if not _is_port_open(args.host, args.port):
            print(json.dumps({"status": "failed", "reason": "Simulator not running and --launch not specified"}, indent=2))
            return 1

    if args.verify:
        smoke = _smoke_rpc(args.host, args.port)
        result["smoke"] = smoke
        if not smoke.get("rpc_ok"):
            print(json.dumps({"status": "failed", "smoke_error": smoke.get("error"), **result}, indent=2))
            return 2

    print(json.dumps({"status": "ok", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
