from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.repositories.drone_fusion_repository import get_drone_fusion_repository
from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.repositories.incident_repository import get_incident_repository
from app.services.camera_registry import get_camera_registry
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager


def main() -> int:
    sim = get_drone_simulation_service()
    manager = get_drone_simulation_session_manager()
    mission_repo = get_drone_mission_repository()
    incident_repo = get_incident_repository()
    fusion_repo = get_drone_fusion_repository()

    runtime = sim.get_runtime_status()
    session = manager.get_session_status()
    sessions = mission_repo.list_sessions(limit=50)
    last_mission = sessions[-1].model_dump(mode="json") if sessions else None
    drone_events = incident_repo.list_events({"source_type": "drone_simulation", "limit": 5000})
    pending_fusion = fusion_repo.list_correlations(review_status="pending", limit=500)

    camera_registry = get_camera_registry()
    camera_items = [
        item for item in camera_registry.list_cameras()
        if (item.metadata or {}).get("source_type") == "drone_simulation" or item.source_type == "drone_simulation"
    ]
    online = sum(1 for item in camera_items if item.status == "online")

    payload = {
        "status": "ok",
        "drone_runtime_status": runtime.model_dump(mode="json"),
        "active_mission_status": session.status,
        "last_mission": last_mission,
        "frames_processed": session.frames_processed_total,
        "drone_origin_event_count": len(drone_events),
        "fusion_candidate_count": len(pending_fusion),
        "stream_camera_health": {
            "registered_drone_sources": len(camera_items),
            "online_sources": online,
            "degraded_sources": len(camera_items) - online,
        },
        "simulated": True,
        "operator_review_required": True,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
