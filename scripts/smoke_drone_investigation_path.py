from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models.investigation_models import PathReconstructionRequest
from app.models.security_models import UserAccount
from app.repositories.gis_repository import get_gis_repository
from app.repositories.incident_repository import get_incident_repository
from app.repositories.investigation_repository import get_investigation_repository
from app.services.drone.drone_simulation_service import DroneSimulationService
from app.services.path_reconstruction_service import reconstruct_path

FORBIDDEN = {
    "suspect confirmed",
    "identity confirmed",
    "target confirmed",
    "criminal confirmed",
    "attacker confirmed",
    "guilty",
    "real drone pursuit",
    "confirmed terrorist",
    "confirmed threat",
}


def _operator() -> UserAccount:
    now = time.time()
    return UserAccount(
        user_id="phase55_inv_operator",
        username="phase55_inv_operator",
        display_name="Phase55 Investigator",
        role="admin",
        status="active",
        password_hash="x",
        created_at=now,
        updated_at=now,
    )


def main() -> int:
    service = DroneSimulationService()
    status = service.connect()
    telemetry = service.get_telemetry() if status.connected else None
    frame = service.get_frame() if status.connected else None
    event_id = "phase55_no_event"
    if telemetry is not None and telemetry.status == "connected":
        obs = service.create_observation_event(observation_type="telemetry", telemetry=telemetry, frame=frame, confidence=0.55)
        service.persist_observation_event(obs, telemetry=telemetry, frame_index=frame.frame_index)
        event_id = obs.event_id
    else:
        recent = get_incident_repository().list_events({"source_type": "drone_simulation", "limit": 1})
        if recent:
            event_id = recent[-1].event_id

    request = PathReconstructionRequest(
        case_id="phase55_demo_case",
        event_id=event_id,
        backward_minutes=15,
        forward_minutes=20,
    )
    response = reconstruct_path(request, get_gis_repository(), get_investigation_repository(), _operator())

    has_forbidden = False
    for hyp in response.hypotheses:
        summary = str(hyp.safe_summary or "").lower()
        if any(term in summary for term in FORBIDDEN):
            has_forbidden = True
            break

    payload = {
        "status": "ok" if not has_forbidden else "failed",
        "path_status": response.status,
        "hypothesis_count": len(response.hypotheses),
        "message": response.message,
        "result_label": "possible_movement_path" if response.hypotheses else "insufficient_data",
        "runtime_connected": bool(status.connected),
        "operator_review_required": True,
        "simulated": True,
    }
    print(json.dumps(payload, indent=2))
    if has_forbidden:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
