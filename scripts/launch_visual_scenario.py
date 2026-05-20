"""
Phase XI — Visual Scenario Launch Script
scripts/launch_visual_scenario.py

Standalone entry point that connects to the running Cosys-AirSim / AirSim
binary, renders the bank_robbery_demo visual scene, and animates actors
along their Phase 6/7 waypoints.

Usage examples
--------------
# Draw static scene only (zones, cameras, actors, drone route):
python scripts/launch_visual_scenario.py --mode setup

# Draw static scene + animate for 65 seconds (full scenario duration):
python scripts/launch_visual_scenario.py --mode full

# Animate only, skip static draw (use if scene already set up):
python scripts/launch_visual_scenario.py --mode animate --duration 65

# Dry-run: validate config without connecting to AirSim:
python scripts/launch_visual_scenario.py --dry-run

# Clear all debug markers from a running AirSim instance:
python scripts/launch_visual_scenario.py --mode flush

Prerequisites
-------------
1. AirSim binary running (AirSimNH, CityEnviron, or Blocks)
2. cosysairsim or airsim Python package installed, OR
   AEGIS_COSYS_AIRSIM_PYTHONCLIENT_DIR env var pointing to PythonClient dir
3. Backend virtual environment activated (or top-level project virtualenv)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase XI — Launch Aegis visual scenario in AirSim"
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "animate", "full", "flush", "status"],
        default="full",
        help=(
            "setup=draw static scene only; "
            "animate=animate actors only; "
            "full=setup+animate; "
            "flush=clear markers; "
            "status=print controller status"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=65.0,
        help="Animation duration in scenario seconds (default: 65)",
    )
    parser.add_argument(
        "--rtf",
        type=float,
        default=1.0,
        help="Real-time factor: 1.0=real-time, 2.0=2x speed (default: 1.0)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("AEGIS_AIRSIM_HOST", "127.0.0.1"),
        help="AirSim host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AEGIS_AIRSIM_PORT", "41451")),
        help="AirSim port (default: 41451)",
    )
    parser.add_argument(
        "--vehicle",
        default=os.environ.get("AEGIS_AIRSIM_VEHICLE", "Drone1"),
        help="AirSim vehicle name (default: Drone1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and report without connecting to AirSim",
    )
    parser.add_argument(
        "--json",
        dest="print_json",
        action="store_true",
        help="Print results as JSON",
    )
    return parser.parse_args()


def _print_banner() -> None:
    print()
    print("=" * 60)
    print("  Phase XI — Visual Simulation World Enrichment")
    print("  Bank Robbery Visual Scenario — Aegis/Sentinel-AI")
    print("=" * 60)
    print()


def _print_result(label: str, result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps({label: result}, indent=2))
    else:
        print(f"\n[{label}]")
        for k, v in result.items():
            print(f"  {k}: {v}")


def main() -> int:
    args = _parse_args()

    if not args.print_json:
        _print_banner()

    from app.services.visual_scenario_controller import AegisVisualScenarioController

    ctrl = AegisVisualScenarioController(
        host=args.host,
        port=args.port,
        vehicle_name=args.vehicle,
        real_time_factor=args.rtf,
        dry_run=args.dry_run,
    )

    # ── status ─────────────────────────────────────────────────────────
    if args.mode == "status":
        status = ctrl.get_status()
        _print_result("status", status, args.print_json)
        return 0

    # ── flush ──────────────────────────────────────────────────────────
    if args.mode == "flush":
        if not args.dry_run:
            connected = ctrl.connect()
            if not connected:
                print("ERROR: Could not connect to AirSim — nothing to flush")
                return 1
        ctrl.flush_markers()
        result = {"flushed": True, "dry_run": args.dry_run}
        _print_result("flush", result, args.print_json)
        return 0

    # ── connect (for setup / animate / full) ───────────────────────────
    if not args.dry_run:
        print(f"  Connecting to AirSim at {args.host}:{args.port} ...")
        connected = ctrl.connect()
        if not connected:
            print(
                "\n  WARNING: AirSim not reachable.\n"
                "  Start one of these runtimes first:\n"
                "    AirSimNH.exe   (Neighborhood — recommended)\n"
                "    CityEnviron.exe (City)\n"
                "    Blocks.exe      (Minimal fallback)\n"
                "  Expected path: C:\\AegisExternalTools\\drone_sim\\runtime\\environments\\\n"
                "\n  Running in dry-run (config validation) mode instead."
            )
            args.dry_run = True
            ctrl._dry_run = True
        else:
            print("  AirSim connection: OK")

    # ── setup ──────────────────────────────────────────────────────────
    if args.mode in ("setup", "full"):
        print("\n  Drawing static scene elements ...")
        t0 = time.time()
        result = ctrl.setup_static_scene()
        elapsed = time.time() - t0
        if not args.print_json:
            print(f"  Zones drawn:          {result.get('zones', 0)}")
            print(f"  Camera markers drawn: {result.get('camera_markers', 0)}")
            print(f"  Actor proxies drawn:  {result.get('actors', 0)}")
            print(f"  Drone route drawn:    {result.get('drone_route', False)}")
            print(f"  Crime markers drawn:  {result.get('crime_markers', 0)}")
            if result.get("dry_run"):
                print("  [DRY-RUN] No AirSim connection — config validated only")
            elif result.get("error"):
                print(f"  WARNING: {result['error']}")
            print(f"  Setup time: {elapsed:.2f}s")
        else:
            _print_result("setup", result, True)

        if args.mode == "setup":
            return 0

    # ── animate ────────────────────────────────────────────────────────
    if args.mode in ("animate", "full"):
        if args.dry_run:
            print(
                "\n  [DRY-RUN] Skipping animation (no AirSim connection).\n"
                "  Animation would run for {:.0f}s at {:.1f}x real-time speed.".format(
                    args.duration, args.rtf
                )
            )
            return 0

        print(
            f"\n  Starting animation:\n"
            f"    Duration:          {args.duration:.0f} scenario seconds\n"
            f"    Real-time factor:  {args.rtf:.2f}x\n"
            f"    Wall-clock time:   ~{args.duration / args.rtf:.0f}s\n"
            f"    Actors:            {list(ctrl._actors.keys())}\n"
        )

        print("  " + "─" * 50)
        print("  t=0s   Suspect enters Financial District")
        print("  t=10s  Civilians arrive at bank")
        print("  t=15s  !! ARMED SUSPECT — weapon detected !!")
        print("  t=20s  Civilians scatter / Security guard responds")
        print("  t=25s  DRONE-ALPHA dispatched")
        print("  t=35s  Escape vehicle contact / alley sequence")
        print("  t=50s  Road checkpoint — intercept point")
        print("  t=60s  Scenario complete")
        print("  " + "─" * 50)
        print()

        try:
            ctrl.run_animation(duration=args.duration)
        except KeyboardInterrupt:
            print("\n  Animation interrupted by user")
            ctrl.stop_animation()

        if not args.print_json:
            print(f"\n  Animation finished at t={ctrl._state.elapsed:.1f}s")
        else:
            _print_result(
                "animate",
                {"elapsed": ctrl._state.elapsed, "completed": True},
                True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
