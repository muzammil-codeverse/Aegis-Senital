from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

try:
    from scripts.drone_runtime_catalog import (
        DEFAULT_HOST,
        DEFAULT_INVENTORY_PATH,
        DEFAULT_PORT,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        load_inventory,
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
        load_inventory,
        persist_inventory,
        select_runtime,
    )


def _load_client_module():
    try:
        import cosysairsim as module

        return module
    except Exception:
        import airsim as module

        return module


def _selected_runtime(runtime_root: Path, prefer: str, fallback: str) -> dict:
    inventory = load_inventory(DEFAULT_INVENTORY_PATH)
    selected_name = str(inventory.get("selected_runtime") or "").strip()
    if selected_name:
        runtime_map = (inventory.get("runtimes") or {}).get(selected_name)
        if runtime_map:
            chosen = dict(runtime_map)
            chosen["fallback_used"] = selected_name == "Blocks"
            return chosen
    return select_runtime(prefer=prefer, fallback=fallback, runtime_root=runtime_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test city runtime RPC/telemetry/frame readiness.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-city", action="store_true")
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--fallback", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()
    selected = _selected_runtime(runtime_root, args.prefer, args.fallback)
    selected_name = str(selected.get("name") or "unknown")
    fallback_used = bool(selected.get("fallback_used") or selected_name == "Blocks")

    if args.require_city and not args.allow_fallback and selected_name == "Blocks":
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "strict city runtime required; Blocks fallback selected",
                    "selected_runtime": selected_name,
                    "fallback_used": True,
                },
                indent=2,
            )
        )
        return 1

    try:
        module = _load_client_module()
        client = module.MultirotorClient(ip=args.host, port=args.port)
        client.confirmConnection()
        state = client.getMultirotorState()
        gps = getattr(state, "gps_location", None)
        image_request = module.ImageRequest("front_center", module.ImageType.Scene, False, False)
        response = client.simGetImages([image_request])[0]
    except Exception as exc:
        payload = {
            "status": "failed",
            "reason": f"RPC failure: {exc}",
            "selected_runtime": selected_name,
            "fallback_used": fallback_used,
            "strict": bool(args.strict),
        }
        print(json.dumps(payload, indent=2))
        return 1

    width = int(getattr(response, "width", 0) or 0)
    height = int(getattr(response, "height", 0) or 0)
    if width <= 0 or height <= 0:
        payload = {
            "status": "failed",
            "reason": "front_center frame is empty",
            "selected_runtime": selected_name,
            "fallback_used": fallback_used,
        }
        print(json.dumps(payload, indent=2))
        return 1

    frame = np.frombuffer(getattr(response, "image_data_uint8", b""), dtype=np.uint8)
    frame = frame.reshape(height, width, 3)
    output_path = Path("storage/drone_sim/city_smoke_frame.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), frame)

    payload = {
        "status": "ok",
        "selected_runtime": selected_name,
        "fallback_used": fallback_used,
        "rpc_ok": True,
        "telemetry_ok": True,
        "front_center_frame_ok": True,
        "city_smoke_frame": str(output_path.resolve()),
        "frame_width": width,
        "frame_height": height,
        "gps": {
            "latitude": float(getattr(gps, "latitude", 0.0) or 0.0) if gps is not None else None,
            "longitude": float(getattr(gps, "longitude", 0.0) or 0.0) if gps is not None else None,
            "altitude": float(getattr(gps, "altitude", 0.0) or 0.0) if gps is not None else None,
        },
    }

    inventory = discover_runtime_inventory(runtime_root)
    inventory["selected_runtime"] = selected_name
    inventory["selected_runtime_details"] = selected
    inventory["city_smoke"] = payload
    persist_inventory(inventory, DEFAULT_INVENTORY_PATH)

    print(json.dumps(payload, indent=2))

    if args.require_city and not args.allow_fallback and fallback_used:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
