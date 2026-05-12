#!/usr/bin/env python3
"""Seed demo GIS profiles for local development (non-sensitive coordinates).

Writes JSONL under storage/gis/ — paths match configs/runtime/gis.yaml defaults.
Do not commit generated files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.models.gis_models import CameraGeoProfile, GeoFenceZone, GeoPoint  # noqa: E402


DEMO_CITIES = {
    "multan": (30.1575, 71.5249),
    "lahore": (31.5204, 74.3587),
    "islamabad": (33.6844, 73.0479),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="multan")
    parser.add_argument("--profile", default="safe_demo")
    args = parser.parse_args()
    lat0, lon0 = DEMO_CITIES.get(args.city.lower(), DEMO_CITIES["multan"])

    out_dir = ROOT / "storage" / "gis"
    out_dir.mkdir(parents=True, exist_ok=True)
    cam_path = out_dir / "camera_geo_profiles.jsonl"
    geo_path = out_dir / "geofences.jsonl"

    profiles = [
        CameraGeoProfile(
            camera_id="demo_cam_01",
            name="Demo perimeter camera 01",
            latitude=lat0 + 0.001,
            longitude=lon0 + 0.001,
            altitude_meters=10.0,
            heading_degrees=45.0,
            fov_degrees=75.0,
            coverage_radius_meters=80.0,
            region="demo_zone",
            metadata={"seed": args.profile, "city": args.city},
        ),
        CameraGeoProfile(
            camera_id="demo_cam_02",
            name="Demo perimeter camera 02",
            latitude=lat0 - 0.0012,
            longitude=lon0 - 0.0008,
            altitude_meters=12.0,
            heading_degrees=200.0,
            fov_degrees=75.0,
            coverage_radius_meters=90.0,
            region="demo_zone",
            metadata={"seed": args.profile, "city": args.city},
        ),
    ]

    zone = GeoFenceZone(
        zone_id="demo_zone_restricted",
        name="Demo restricted risk zone",
        zone_type="restricted",
        polygon=[
            GeoPoint(latitude=lat0 - 0.002, longitude=lon0 - 0.002),
            GeoPoint(latitude=lat0 + 0.002, longitude=lon0 - 0.002),
            GeoPoint(latitude=lat0 + 0.002, longitude=lon0 + 0.002),
            GeoPoint(latitude=lat0 - 0.002, longitude=lon0 + 0.002),
        ],
        severity="high",
        metadata={"seed": args.profile},
    )

    cam_path.write_text("\n".join(p.model_dump_json() for p in profiles) + "\n", encoding="utf-8")
    geo_path.write_text(zone.model_dump_json() + "\n", encoding="utf-8")
    print(f"Wrote {cam_path} and {geo_path}")


if __name__ == "__main__":
    main()
