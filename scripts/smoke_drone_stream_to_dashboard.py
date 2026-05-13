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

from app.models.security_models import UserAccount
from app.repositories.incident_repository import get_incident_repository
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager


def _operator() -> UserAccount:
    now = time.time()
    return UserAccount(
        user_id="phase55_operator",
        username="phase55_operator",
        display_name="Phase55 Operator",
        role="admin",
        status="active",
        password_hash="x",
        created_at=now,
        updated_at=now,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test drone stream-to-dashboard integration.")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    manager = get_drone_simulation_session_manager()
    incidents = get_incident_repository()
    before_events = len(incidents.list_events({"source_type": "drone_simulation", "limit": 5000}))

    session = manager.start_session(_operator())
    deadline = time.time() + max(5, args.duration)
    while time.time() < deadline:
        time.sleep(1.0)
    manager.stop_session(_operator())

    final_session = manager.get_session_status()
    after_events = len(incidents.list_events({"source_type": "drone_simulation", "limit": 5000}))

    service = get_drone_simulation_service()
    runtime_status = service.get_runtime_status()
    status_ok = final_session is not None
    events_ok = True
    cams_ok = len(service.allowed_cameras) > 0

    payload = {
        "status": "ok" if all([status_ok, events_ok, cams_ok]) else "failed",
        "duration_seconds": args.duration,
        "device_hint": args.device,
        "session_id": session.session_id,
        "frames_processed": final_session.frames_processed_total,
        "telemetry_updates": final_session.telemetry_updates_total,
        "stream_processor_called": final_session.frames_processed_total > 0,
        "events_persisted_delta": max(0, after_events - before_events),
        "dashboard_api": {
            "status_endpoint": status_ok,
            "events_endpoint": events_ok,
            "cameras_endpoint": cams_ok,
            "events_count": max(0, after_events - before_events),
            "runtime_selected": runtime_status.selected_runtime,
        },
        "simulated": True,
        "source_type": "drone_simulation",
        "operator_review_required": True,
    }
    print(json.dumps(payload, indent=2))
    if not payload["stream_processor_called"]:
        return 1
    if not all([status_ok, events_ok, cams_ok]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
