from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.drone.drone_simulation_service import DroneSimulationService


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify multi-camera capture for drone simulation.")
    parser.add_argument("--require-cameras", default="front_center,front_left,front_right,downward,rear")
    parser.add_argument("--retries", type=int, default=8)
    args = parser.parse_args()

    required = [item.strip().lower() for item in str(args.require_cameras).split(",") if item.strip()]
    service = DroneSimulationService()
    status = service.connect()
    if not status.connected:
        print(json.dumps({"status": "failed", "reason": status.last_error or "runtime unavailable"}, indent=2))
        return 1

    frames = []
    for _ in range(max(1, args.retries)):
        frames = service.get_multi_camera_frames(required)
        if any(frame.frame_available for frame in frames):
            break
        time.sleep(0.4)

    frame_map = {frame.camera_name: frame for frame in frames}
    report = {
        "status": "ok",
        "required_cameras": required,
        "results": [],
    }

    hard_fail = False
    for name in required:
        frame = frame_map.get(name)
        if frame is None:
            report["results"].append({"camera": name, "frame_available": False, "reason": "camera did not return a response"})
            if name in {"front_center", "downward"}:
                hard_fail = True
            continue
        item = {
            "camera": name,
            "frame_available": bool(frame.frame_available),
            "width": frame.width,
            "height": frame.height,
            "status": frame.status,
            "reason": frame.last_error,
        }
        report["results"].append(item)
        if name == "front_center" and not frame.frame_available:
            hard_fail = True
        if name == "downward" and not frame.frame_available:
            hard_fail = True

    report["front_center_required"] = True
    report["downward_required_for_demo"] = True
    report["hard_fail"] = hard_fail
    report["source"] = "simulated_drone_runtime"

    print(json.dumps(report, indent=2))
    service.disconnect()
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
