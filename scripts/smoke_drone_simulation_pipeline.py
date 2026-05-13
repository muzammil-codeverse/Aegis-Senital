#!/usr/bin/env python3
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

from app.services.drone.drone_frame_adapter import DroneFrameAdapter
from app.services.drone.drone_simulation_service import DroneSimulationService


def _run_stream_processor(packet, device: str) -> tuple[bool, dict, str | None]:
    try:
        from inference.model_pool import get_model_pool
        from inference.stream.stream_processor import StreamProcessor
        from ml.runtime import ModelRouter, system_boot_check

        pool = get_model_pool()
        if not pool.is_loaded:
            system_boot_check()
            router = ModelRouter()
            weapon = router.get_model("weapon")
            phone = router.get_model("phone")
            pool.load(weapon_path=weapon["resolved_path"], phone_path=phone["resolved_path"], device=device)

        processor = StreamProcessor(
            stream_id="cam_drone_sim_01",
            source="cosys_airsim://drone_sim_01",
            model_pool=pool,
        )
        processor.source_type = "drone_simulation"
        result = processor.process_decoded_packet(packet)
        return True, result, None
    except Exception as exc:
        return False, {}, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test simulated drone pipeline through StreamProcessor.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()

    service = DroneSimulationService()
    status = service.connect()
    if not status.connected:
        print(json.dumps({"status": "failed", "reason": status.last_error or "runtime unavailable"}, indent=2))
        return 1 if args.strict else 0

    deadline = time.time() + max(5, args.duration)
    frames_processed = 0
    inference_attempted = False
    last_error = None
    aggregates = {"events": 0, "anomalies": 0, "incidents": 0, "scenarios": 0}

    while time.time() < deadline:
        telemetry = service.get_telemetry()
        frame = service.get_frame()
        if telemetry.status != "connected" or not frame.frame_available:
            time.sleep(0.2)
            continue
        packet = DroneFrameAdapter.to_decoded_packet(frame, telemetry)
        ok, result, err = _run_stream_processor(packet, args.device)
        inference_attempted = True
        if ok:
            frames_processed += 1
            aggregates["events"] += len(result.get("events") or [])
            aggregates["anomalies"] += len(result.get("anomalies") or [])
            aggregates["incidents"] += len(result.get("incidents") or [])
            aggregates["scenarios"] += len(result.get("scenarios") or [])
        else:
            last_error = err
        time.sleep(0.1)

    service.disconnect()

    payload = {
        "status": "ok" if frames_processed > 0 and inference_attempted else "failed",
        "frames_processed": frames_processed,
        "model_inference_attempted": inference_attempted,
        "no_crash": last_error is None,
        "last_error": last_error,
        "outputs": aggregates,
        "safe_labels": [
            "Simulated aerial observation",
            "Candidate cross-source observation",
            "Operator review required",
        ],
    }
    print(json.dumps(payload, indent=2))
    if args.strict and payload["status"] != "ok":
        return 1
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
