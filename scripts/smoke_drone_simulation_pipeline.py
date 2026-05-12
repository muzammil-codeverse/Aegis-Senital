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

from app.services.drone.drone_simulation_service import DroneSimulationService
from inference.drone.drone_frame_adapter import DroneFrameAdapter


def _process_packet_with_stream_processor(packet, device: str) -> tuple[str, dict]:
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
            pool.load(
                weapon_path=weapon["resolved_path"],
                phone_path=phone["resolved_path"],
                device=device,
            )
        processor = StreamProcessor(
            stream_id="cam_drone_sim_01",
            source="cosys_airsim://drone_sim_01",
            model_pool=pool,
        )
        processor.source_type = "drone_simulation"
        result = processor.process_decoded_packet(packet)
        return "stream_processor", {
            "events": len(result.get("events") or []),
            "anomalies": len(result.get("anomalies") or []),
            "incidents": len(result.get("incidents") or []),
            "scenarios": len(result.get("scenarios") or []),
        }
    except Exception as exc:
        return "adapter_only", {
            "warning": f"StreamProcessor unavailable for smoke path: {exc}",
            "events": 0,
            "anomalies": 0,
            "incidents": 0,
            "scenarios": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the simulated drone integration pipeline.")
    parser.add_argument("--strict", action="store_true", help="Fail if the simulator is unavailable.")
    parser.add_argument("--device", default="auto", help="Inference device hint for StreamProcessor smoke.")
    parser.add_argument("--max-frames", type=int, default=30, help="Maximum frame capture attempts before giving up.")
    args = parser.parse_args()

    service = DroneSimulationService()
    status = service.connect()
    if not status.connected:
        message = status.last_error or "Simulated drone runtime is unavailable."
        print(message)
        return 1 if args.strict else 0

    telemetry = None
    frame = None
    for _ in range(max(1, args.max_frames)):
        telemetry = service.get_telemetry()
        frame = service.get_frame()
        if telemetry.status == "connected" and frame.frame_available:
            break
        time.sleep(0.1)

    if telemetry is None or telemetry.status == "disconnected":
        print("Simulated telemetry could not be retrieved from the connected runtime.")
        service.disconnect()
        return 1 if args.strict else 0
    if frame is None or not frame.frame_available:
        print("No simulated frame was available from the runtime during smoke capture.")
        service.disconnect()
        return 1 if args.strict else 0

    packet = DroneFrameAdapter.to_decoded_packet(frame, telemetry)
    mode, processing = _process_packet_with_stream_processor(packet, args.device)

    payload = {
        "status": "ok",
        "mode": mode,
        "source_type": packet.metadata.get("source_type"),
        "camera_id": packet.metadata.get("camera_id"),
        "drone_id": packet.metadata.get("drone_id"),
        "simulated": packet.metadata.get("simulated"),
        "telemetry_status": telemetry.status,
        "frame_index": frame.frame_index,
        "processing": processing,
    }
    print(json.dumps(payload, indent=2))
    service.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
