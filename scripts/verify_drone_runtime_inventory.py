from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.drone_runtime_catalog import (
        DEFAULT_INVENTORY_PATH,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        load_inventory,
        persist_inventory,
        select_runtime,
    )
except ModuleNotFoundError:
    from drone_runtime_catalog import (  # type: ignore[no-redef]
        DEFAULT_INVENTORY_PATH,
        DEFAULT_RUNTIME_ROOT,
        discover_runtime_inventory,
        load_inventory,
        persist_inventory,
        select_runtime,
    )


def _failed(msg: str, payload: dict) -> int:
    print(json.dumps({"status": "failed", "reason": msg, **payload}, indent=2))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify drone runtime inventory for city/neighborhood/fallback readiness.")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    parser.add_argument("--require-city", action="store_true", help="Require CityEnviron or AirSimNH selection (Blocks alone fails).")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--fallback", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).resolve()
    discovered = discover_runtime_inventory(runtime_root)
    previous = load_inventory(DEFAULT_INVENTORY_PATH)
    selected = select_runtime(prefer=args.prefer, fallback=args.fallback, runtime_root=runtime_root)

    discovered["selected_runtime"] = selected.get("name")
    discovered["selected_runtime_details"] = selected
    discovered["previous_download_status"] = previous.get("download_status")
    persist_inventory(discovered, DEFAULT_INVENTORY_PATH)

    runtimes = discovered.get("runtimes") or {}
    blocks = runtimes.get("Blocks") or {}
    airsimnh = runtimes.get("AirSimNH") or {}
    city = runtimes.get("CityEnviron") or {}

    if not blocks.get("available"):
        return _failed("Blocks fallback runtime is missing.", {"inventory": discovered})

    airsimnh_ok = bool(airsimnh.get("available"))
    city_ok = bool(city.get("available"))

    documented_failure = False
    download_status = previous.get("download_status") or {}
    if str(download_status.get("status") or "").lower() == "failed":
        documented_failure = bool(download_status.get("reason"))

    if not airsimnh_ok and not documented_failure:
        return _failed(
            "AirSimNH is missing and no exact download failure is recorded.",
            {"inventory": discovered, "download_status": download_status},
        )

    selected_name = str(selected.get("name") or "")
    fallback_used = bool(selected.get("fallback_used"))
    selected_runtime_type = str(selected.get("runtime_type") or "unknown")
    selected_exe = selected.get("executable_path")

    if selected_name and not selected_exe:
        return _failed("Selected runtime does not have an executable path.", {"inventory": discovered})

    if args.require_city:
        if selected_name not in {"CityEnviron", "AirSimNH"}:
            return _failed(
                "Strict city requirement failed: selected runtime is fallback Blocks.",
                {
                    "inventory": discovered,
                    "strict_city": False,
                    "fallback_used": fallback_used,
                },
            )

    payload = {
        "status": "ok",
        "runtime_root": str(runtime_root),
        "blocks": blocks,
        "airsimnh": airsimnh,
        "cityenviron": city,
        "selected_runtime": selected_name,
        "selected_runtime_type": selected_runtime_type,
        "executable_path": selected_exe,
        "fallback_used": fallback_used,
        "strict_city": selected_name in {"CityEnviron", "AirSimNH"},
        "download_status": download_status,
        "inventory_path": str(DEFAULT_INVENTORY_PATH.resolve()),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
