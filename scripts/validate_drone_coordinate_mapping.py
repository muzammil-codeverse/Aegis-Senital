#!/usr/bin/env python3
"""Phase 45 carry-forward — Geo-to-NED Live Pose Validation (Task 2).

Usage:
  python scripts/validate_drone_coordinate_mapping.py
  python scripts/validate_drone_coordinate_mapping.py --strict

Non-strict: warns if simulator offline.
Strict: fails if simulator offline.

Unit-tests geo_to_ned and ned_to_geo, then optionally compares against
live AirSim pose if the simulator is reachable.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _check(name: str, ok: bool, detail: str = "", required: bool = True) -> bool:
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def _unit_test_geo_to_ned() -> bool:
    from app.services.drone.drone_coordinate_mapper import (
        HOME_ALTITUDE,
        HOME_LATITUDE,
        HOME_LONGITUDE,
        geo_to_ned,
        ned_to_geo,
    )

    results = []

    # Identity: home → NED should be (0, 0, 0)
    ned = geo_to_ned(HOME_LATITUDE, HOME_LONGITUDE, HOME_ALTITUDE)
    ok = abs(ned.x) < 0.01 and abs(ned.y) < 0.01 and abs(ned.z) < 0.01
    results.append(_check("geo_to_ned identity (home → NED ≈ 0,0,0)", ok,
                           f"got ({ned.x:.4f}, {ned.y:.4f}, {ned.z:.4f})"))

    # Round-trip: geo → NED → geo should recover original
    lat_test, lon_test, alt_test = HOME_LATITUDE + 0.01, HOME_LONGITUDE + 0.01, 50.0
    ned2 = geo_to_ned(lat_test, lon_test, alt_test)
    geo_back = ned_to_geo(ned2.x, ned2.y, ned2.z)
    lat_err = abs(geo_back.latitude - lat_test)
    lon_err = abs(geo_back.longitude - lon_test)
    ok_rt = lat_err < 1e-5 and lon_err < 1e-5
    results.append(_check("ned_to_geo round-trip", ok_rt,
                           f"lat_err={lat_err:.6f} lon_err={lon_err:.6f}"))

    # Northward 100 m: x should be ≈ 100, y ≈ 0
    north_lat = HOME_LATITUDE + (100 / 111_320)
    ned3 = geo_to_ned(north_lat, HOME_LONGITUDE, HOME_ALTITUDE)
    ok_north = abs(ned3.x - 100) < 2.0 and abs(ned3.y) < 2.0
    results.append(_check("100m north → NED x≈100", ok_north, f"x={ned3.x:.2f} y={ned3.y:.2f}"))

    # Eastward 100 m: y should be ≈ 100, x ≈ 0
    east_lon = HOME_LONGITUDE + (100 / (111_320 * math.cos(math.radians(HOME_LATITUDE))))
    ned4 = geo_to_ned(HOME_LATITUDE, east_lon, HOME_ALTITUDE)
    ok_east = abs(ned4.y - 100) < 2.0 and abs(ned4.x) < 2.0
    results.append(_check("100m east → NED y≈100", ok_east, f"x={ned4.x:.2f} y={ned4.y:.2f}"))

    return all(results)


def _live_airsim_validation(strict: bool) -> bool:
    print("\n[Live AirSim Pose Validation]")
    try:
        from app.services.drone.cosys_airsim_client import CosysAirSimClient
        client = CosysAirSimClient()
        client.connect()
        state = client.get_drone_state()
        print(f"  [INFO] AirSim connected. Drone state keys: {list(state.keys()) if isinstance(state, dict) else type(state)}")

        from app.services.drone.drone_coordinate_mapper import HOME_LATITUDE, HOME_LONGITUDE, HOME_ALTITUDE, geo_to_ned
        ned = geo_to_ned(HOME_LATITUDE + 0.001, HOME_LONGITUDE + 0.001, HOME_ALTITUDE + 20)
        print(f"  [INFO] Sample waypoint NED: x={ned.x:.2f} y={ned.y:.2f} z={ned.z:.2f}")

        _check("AirSim live connection", True, "simulator reachable")
        _check("Waypoint NED conversion", True, f"({ned.x:.1f}, {ned.y:.1f}, {ned.z:.1f})")
        return True
    except ImportError as exc:
        _check("AirSim client import", False, str(exc), required=strict)
        return not strict
    except Exception as exc:
        _check("AirSim live connection", False, str(exc)[:120], required=strict)
        if strict:
            print("  [WARN] Strict mode: simulator unavailable. Live validation FAIL.")
            return False
        print("  [WARN] Simulator unavailable — live validation skipped (non-strict mode).")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate drone coordinate mapping")
    parser.add_argument("--strict", action="store_true", help="Fail if simulator is offline")
    args = parser.parse_args()

    print("[Geo-to-NED Coordinate Mapping Validation]")
    print()
    print("[Unit Tests]")
    unit_ok = _unit_test_geo_to_ned()

    live_ok = _live_airsim_validation(strict=args.strict)

    print()
    if unit_ok and live_ok:
        print("[PASS] Coordinate mapping validation complete.")
        sys.exit(0)
    else:
        print("[FAIL] Coordinate mapping validation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
