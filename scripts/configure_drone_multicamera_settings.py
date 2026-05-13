from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _build_camera_capture_settings(width: int, height: int, fov: int, include_optional_types: bool) -> list[dict[str, Any]]:
    capture = [
        {
            "ImageType": 0,
            "Width": width,
            "Height": height,
            "FOV_Degrees": fov,
        }
    ]
    if include_optional_types:
        capture.extend(
            [
                {"ImageType": 1, "Width": width, "Height": height, "FOV_Degrees": fov},
                {"ImageType": 5, "Width": width, "Height": height, "FOV_Degrees": fov},
            ]
        )
    return capture


def _build_settings(profile: str) -> dict[str, Any]:
    include_optional_types = profile in {"city_demo", "full"}
    width = 1280
    height = 720

    camera_definitions = {
        "front_center": _build_camera_capture_settings(width, height, 90, include_optional_types),
        "front_left": _build_camera_capture_settings(width, height, 90, include_optional_types),
        "front_right": _build_camera_capture_settings(width, height, 90, include_optional_types),
        "downward": _build_camera_capture_settings(width, height, 110, include_optional_types),
        "rear": _build_camera_capture_settings(width, height, 90, include_optional_types),
    }

    cameras = {
        camera_name: {"CaptureSettings": capture_settings}
        for camera_name, capture_settings in camera_definitions.items()
    }

    return {
        "SettingsVersion": 1.2,
        "SimMode": "Multirotor",
        "ClockType": "ScalableClock",
        "ViewMode": "SpringArmChase",
        "Vehicles": {
            "Drone1": {
                "VehicleType": "SimpleFlight",
                "AutoCreate": True,
                "EnableCollisionPassthrogh": False,
                "Cameras": cameras,
            }
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multi-camera AirSim settings for city drone demo.")
    parser.add_argument("--profile", default="city_demo", choices=["city_demo", "minimal", "full"])
    args = parser.parse_args()

    airsim_dir = Path.home() / "Documents" / "AirSim"
    airsim_dir.mkdir(parents=True, exist_ok=True)
    settings_path = airsim_dir / "settings.json"

    if settings_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = airsim_dir / f"settings.backup.{timestamp}.json"
        backup_path.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing settings to: {backup_path}")

    settings = _build_settings(args.profile)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"Wrote multi-camera settings: {settings_path}")
    print(
        json.dumps(
            {
                "profile": args.profile,
                "vehicle": "Drone1",
                "cameras": ["front_center", "front_left", "front_right", "downward", "rear"],
                "resolution": "1280x720",
                "scene_image_type": 0,
                "optional_image_types": [1, 5] if args.profile in {"city_demo", "full"} else [],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
