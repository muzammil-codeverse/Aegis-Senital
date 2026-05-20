from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.scenario_models import (
    ActorRole,
    ScenarioActor,
    ScenarioDefinition,
    ScenarioRun,
    ScenarioRunStatus,
    ScenarioState,
    ScenarioTimelineEvent,
)
from app.models.tracking_models import (
    CameraHandoff,
    DroneRoute,
    DroneRouteStatus,
    EntityType,
    FusedTrack,
    FusedTrackStatus,
    PathWaypoint,
    WaypointLocation,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROMOTIONS_DIR = _PROJECT_ROOT / "runtime_state" / "scenario_promotions"
_DRONE_ROUTES_DIR = _PROJECT_ROOT / "runtime_state" / "drone_routes"
_SCENARIO_TRACKING_DIR = _PROJECT_ROOT / "runtime_state" / "scenario_tracking"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# bank_robbery_demo — canonical Phase 6 demonstration scenario
# ---------------------------------------------------------------------------

BANK_ROBBERY_DEMO = ScenarioDefinition(
    scenario_id="bank_robbery_demo",
    name="Bank Robbery / Suspect Escape",
    description=(
        "Armed robbery at Financial District bank followed by suspect escape "
        "through parking lot, alley, and road checkpoints. DRONE-ALPHA dispatched "
        "on weapon detection."
    ),
    category="crime",
    camera_ids=[
        "CAM-BANK-01", "CAM-BANK-02", "CAM-BANK-03",
        "CAM-ROAD-01", "CAM-MARKET-01",
        "CAM-PARKING-01", "CAM-GATE-01", "CAM-ALLEY-01",
    ],
    drone_ids=["DRONE-ALPHA", "DRONE-CHARLIE"],
    actors=[
        ScenarioActor(
            actor_id="SUSPECT-001",
            name="Primary Suspect",
            role=ActorRole.SUSPECT,
            description="Armed suspect executing bank robbery and escape",
            camera_ids=["CAM-BANK-01", "CAM-BANK-02", "CAM-PARKING-01", "CAM-ALLEY-01", "CAM-ROAD-01"],
            zone_id="zone_financial",
        ),
        ScenarioActor(
            actor_id="CIVILIAN-GROUP-001",
            name="Bank Civilian Group",
            role=ActorRole.CIVILIAN,
            description="Group of civilians inside and near the bank during the incident",
            camera_ids=["CAM-BANK-01", "CAM-BANK-02", "CAM-BANK-03"],
            zone_id="zone_financial",
        ),
        ScenarioActor(
            actor_id="SECURITY-GUARD-001",
            name="Bank Security Guard",
            role=ActorRole.SECURITY,
            description="On-duty bank security guard responding to weapon detection",
            camera_ids=["CAM-BANK-01", "CAM-BANK-02"],
            zone_id="zone_financial",
        ),
        ScenarioActor(
            actor_id="ESCAPE-VEHICLE-001",
            name="Escape Vehicle",
            role=ActorRole.VEHICLE,
            description="Getaway vehicle waiting in the parking lot",
            camera_ids=["CAM-PARKING-01", "CAM-GATE-01"],
            zone_id="zone_parking",
        ),
    ],
    timeline=[
        ScenarioTimelineEvent(
            step=0, t_offset_seconds=0,
            event_type="person_tracking",
            description="Routine surveillance: suspicious individual enters Financial District",
            actor_id="SUSPECT-001", camera_id="CAM-BANK-01", zone_id="zone_financial",
            confidence=0.72, severity="low",
            metadata={"phase": "pre_incident", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=1, t_offset_seconds=5,
            event_type="suspicious_person",
            description="Suspect loitering near bank entrance; behaviour flagged",
            actor_id="SUSPECT-001", camera_id="CAM-BANK-01", zone_id="zone_financial",
            confidence=0.78, severity="medium",
            metadata={"phase": "pre_incident", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=2, t_offset_seconds=10,
            event_type="person_tracking",
            description="Civilians entering bank — group of 5 observed",
            actor_id="CIVILIAN-GROUP-001", camera_id="CAM-BANK-02", zone_id="zone_financial",
            confidence=0.65, severity="info",
            metadata={"phase": "pre_incident", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=3, t_offset_seconds=15,
            event_type="weapon_detected",
            description="ARMED SUSPECT: weapon displayed at bank entrance — CRITICAL",
            actor_id="SUSPECT-001", camera_id="CAM-BANK-01", zone_id="zone_financial",
            confidence=0.95, severity="critical",
            detected_class="weapon",
            promote_to_alert=True,
            promote_to_incident=True,
            trigger_drone_dispatch=True,
            metadata={"phase": "active_incident", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=4, t_offset_seconds=20,
            event_type="suspect_movement",
            description="Security guard responding to weapon alarm — bank lockdown initiated",
            actor_id="SECURITY-GUARD-001", camera_id="CAM-BANK-02", zone_id="zone_financial",
            confidence=0.82, severity="high",
            metadata={"phase": "active_incident", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=5, t_offset_seconds=25,
            event_type="drone_observation",
            description="DRONE-ALPHA dispatched — aerial surveillance of Financial District",
            drone_id="DRONE-ALPHA", zone_id="zone_financial",
            confidence=0.90, severity="high",
            metadata={"phase": "drone_response", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=6, t_offset_seconds=30,
            event_type="suspect_movement",
            description="Suspect sighted moving toward parking lot — direction: north",
            actor_id="SUSPECT-001", camera_id="CAM-PARKING-01", zone_id="zone_parking",
            confidence=0.88, severity="high",
            metadata={"phase": "escape_sequence", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=7, t_offset_seconds=35,
            event_type="zone_intrusion",
            description="Escape vehicle detected in restricted parking zone",
            actor_id="ESCAPE-VEHICLE-001", camera_id="CAM-PARKING-01", zone_id="zone_parking",
            confidence=0.85, severity="high",
            metadata={"phase": "escape_sequence", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=8, t_offset_seconds=40,
            event_type="suspect_movement",
            description="Suspect attempting to exit via alley — DRONE-ALPHA tracking",
            actor_id="SUSPECT-001", camera_id="CAM-ALLEY-01", zone_id="zone_alley",
            confidence=0.80, severity="high",
            metadata={"phase": "escape_sequence", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=9, t_offset_seconds=45,
            event_type="drone_observation",
            description="DRONE-ALPHA: aerial confirmation of suspect location — alley sector",
            drone_id="DRONE-ALPHA", zone_id="zone_alley",
            confidence=0.87, severity="medium",
            metadata={"phase": "drone_response", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=10, t_offset_seconds=50,
            event_type="suspect_movement",
            description="Suspect reaching road checkpoint — intercept recommended",
            actor_id="SUSPECT-001", camera_id="CAM-ROAD-01", zone_id="zone_roads",
            confidence=0.75, severity="medium",
            metadata={"phase": "escape_sequence", "simulated": True},
        ),
        ScenarioTimelineEvent(
            step=11, t_offset_seconds=60,
            event_type="scenario_incident",
            description="SCENARIO COMPLETE: Bank robbery incident — full observation timeline captured",
            actor_id="SUSPECT-001", camera_id="CAM-BANK-01", zone_id="zone_financial",
            confidence=0.95, severity="critical",
            promote_to_alert=True,
            promote_to_incident=True,
            metadata={"phase": "summary", "simulated": True},
        ),
    ],
    metadata={"version": "1.0", "author": "sentinel-ai", "exhibition": True},
)

# Catalogue of available scenario definitions
SCENARIO_CATALOGUE: dict[str, ScenarioDefinition] = {
    BANK_ROBBERY_DEMO.scenario_id: BANK_ROBBERY_DEMO,
}


# ---------------------------------------------------------------------------
# bank_robbery_demo — deterministic suspect path waypoints (Phase 7)
# ---------------------------------------------------------------------------

BANK_ROBBERY_SUSPECT_PATH: list[dict[str, Any]] = [
    {
        "waypoint_id": "wp-suspect-00",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 0,
        "location": {"x": 120.0, "y": 80.0, "z": 3.5},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "CAM-BANK-01",
        "source_type": "fixed_cctv",
        "confidence": 0.72,
        "metadata": {"phase": "pre_incident", "description": "Suspect enters Financial District"},
    },
    {
        "waypoint_id": "wp-suspect-01",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 5,
        "location": {"x": 130.0, "y": 85.0, "z": 3.5},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "CAM-BANK-01",
        "source_type": "fixed_cctv",
        "confidence": 0.78,
        "metadata": {"phase": "pre_incident", "description": "Suspect loiters near bank entrance"},
    },
    {
        "waypoint_id": "wp-suspect-02",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 15,
        "location": {"x": 145.0, "y": 100.0, "z": 3.0},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "CAM-BANK-02",
        "source_type": "fixed_cctv",
        "confidence": 0.95,
        "metadata": {"phase": "active_incident", "description": "ARMED: weapon displayed at bank — CRITICAL"},
    },
    {
        "waypoint_id": "wp-suspect-03",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 20,
        "location": {"x": 160.0, "y": 115.0, "z": 3.0},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "CAM-BANK-03",
        "source_type": "ptz_camera",
        "confidence": 0.88,
        "metadata": {"phase": "escape_sequence", "description": "Suspect exits bank — moving north"},
    },
    {
        "waypoint_id": "wp-suspect-04",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 25,
        "location": {"x": 200.0, "y": 145.0, "z": 2.5},
        "zone_id": "zone_market",
        "zone_name": "Market District",
        "source_id": "CAM-MARKET-01",
        "source_type": "ptz_camera",
        "confidence": 0.82,
        "metadata": {"phase": "escape_sequence", "description": "Suspect at market edge"},
    },
    {
        "waypoint_id": "wp-suspect-05",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 30,
        "location": {"x": 260.0, "y": 180.0, "z": 2.5},
        "zone_id": "zone_roads",
        "zone_name": "Main Road",
        "source_id": "CAM-ROAD-01",
        "source_type": "fixed_cctv",
        "confidence": 0.84,
        "metadata": {"phase": "escape_sequence", "description": "Suspect crosses main road"},
    },
    {
        "waypoint_id": "wp-suspect-06",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 35,
        "location": {"x": 310.0, "y": 200.0, "z": 2.0},
        "zone_id": "zone_parking",
        "zone_name": "Parking Zone",
        "source_id": "CAM-PARKING-01",
        "source_type": "ptz_camera",
        "confidence": 0.88,
        "metadata": {"phase": "escape_sequence", "description": "Suspect at parking — escape vehicle contact"},
    },
    {
        "waypoint_id": "wp-suspect-07",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 40,
        "location": {"x": 330.0, "y": 230.0, "z": 2.0},
        "zone_id": "zone_alley",
        "zone_name": "Alley Sector",
        "source_id": "CAM-ALLEY-01",
        "source_type": "fixed_cctv",
        "confidence": 0.80,
        "metadata": {"phase": "escape_sequence", "description": "Suspect enters alley — DRONE-ALPHA tracking"},
    },
    {
        "waypoint_id": "wp-suspect-08",
        "entity_id": "SUSPECT-001",
        "entity_type": "suspect",
        "offset_seconds": 50,
        "location": {"x": 380.0, "y": 260.0, "z": 2.0},
        "zone_id": "zone_roads",
        "zone_name": "Main Road",
        "source_id": "CAM-ROAD-01",
        "source_type": "fixed_cctv",
        "confidence": 0.75,
        "metadata": {"phase": "escape_sequence", "description": "Suspect at road checkpoint — intercept recommended"},
    },
]


# ---------------------------------------------------------------------------
# bank_robbery_demo — camera handoff sequence (Phase 7)
# ---------------------------------------------------------------------------

BANK_ROBBERY_CAMERA_HANDOFFS: list[dict[str, Any]] = [
    {
        "handoff_id": "hoff-01",
        "from_camera_id": "CAM-BANK-01",
        "to_camera_id": "CAM-BANK-02",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 15,
        "reason": "weapon_detected — suspect moves to vault corridor view",
        "confidence": 0.95,
        "metadata": {"trigger": "weapon_detected", "zone": "zone_financial"},
    },
    {
        "handoff_id": "hoff-02",
        "from_camera_id": "CAM-BANK-02",
        "to_camera_id": "CAM-BANK-03",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 18,
        "reason": "suspect_movement — exits vault corridor toward ATM zone",
        "confidence": 0.88,
        "metadata": {"trigger": "suspect_movement", "zone": "zone_financial"},
    },
    {
        "handoff_id": "hoff-03",
        "from_camera_id": "CAM-BANK-03",
        "to_camera_id": "CAM-MARKET-01",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 22,
        "reason": "suspect_movement — exits financial zone toward market district",
        "confidence": 0.82,
        "metadata": {"trigger": "suspect_movement", "zone_from": "zone_financial", "zone_to": "zone_market"},
    },
    {
        "handoff_id": "hoff-04",
        "from_camera_id": "CAM-MARKET-01",
        "to_camera_id": "CAM-ROAD-01",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 27,
        "reason": "suspect_movement — crosses market edge toward main road",
        "confidence": 0.80,
        "metadata": {"trigger": "suspect_movement", "zone_from": "zone_market", "zone_to": "zone_roads"},
    },
    {
        "handoff_id": "hoff-05",
        "from_camera_id": "CAM-ROAD-01",
        "to_camera_id": "CAM-PARKING-01",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 32,
        "reason": "suspect_movement — north toward parking zone",
        "confidence": 0.84,
        "metadata": {"trigger": "suspect_movement", "zone_from": "zone_roads", "zone_to": "zone_parking"},
    },
    {
        "handoff_id": "hoff-06",
        "from_camera_id": "CAM-PARKING-01",
        "to_camera_id": "CAM-ALLEY-01",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 37,
        "reason": "suspect_movement — enters alley after escape vehicle contact",
        "confidence": 0.85,
        "metadata": {"trigger": "suspect_movement", "zone_from": "zone_parking", "zone_to": "zone_alley"},
    },
    {
        "handoff_id": "hoff-07",
        "from_camera_id": "CAM-ALLEY-01",
        "to_camera_id": "CAM-ROAD-01",
        "actor_id": "SUSPECT-001",
        "offset_seconds": 47,
        "reason": "suspect_movement — exits alley to road checkpoint",
        "confidence": 0.78,
        "metadata": {"trigger": "suspect_movement", "drone_tracking": True},
    },
]


# ---------------------------------------------------------------------------
# bank_robbery_demo — DRONE-ALPHA deterministic dispatch route (Phase 7)
# ---------------------------------------------------------------------------

DRONE_ALPHA_ROUTE_WAYPOINTS: list[dict[str, Any]] = [
    {
        "waypoint_id": "drone-wp-00",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 25,
        "location": {"x": 120.0, "y": 80.0, "z": 40.0},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.95,
        "metadata": {"phase": "dispatch", "description": "DRONE-ALPHA home — financial patrol point"},
    },
    {
        "waypoint_id": "drone-wp-01",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 27,
        "location": {"x": 135.0, "y": 90.0, "z": 35.0},
        "zone_id": "zone_financial",
        "zone_name": "Financial District",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.95,
        "metadata": {"phase": "tracking", "description": "Bank roof overview — incident origin"},
    },
    {
        "waypoint_id": "drone-wp-02",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 30,
        "location": {"x": 200.0, "y": 145.0, "z": 30.0},
        "zone_id": "zone_market",
        "zone_name": "Market District",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.90,
        "metadata": {"phase": "tracking", "description": "Market intercept vector — suspect last sighted"},
    },
    {
        "waypoint_id": "drone-wp-03",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 35,
        "location": {"x": 310.0, "y": 200.0, "z": 25.0},
        "zone_id": "zone_parking",
        "zone_name": "Parking Zone",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.87,
        "metadata": {"phase": "tracking", "description": "Parking overhead — escape vehicle intercept"},
    },
    {
        "waypoint_id": "drone-wp-04",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 42,
        "location": {"x": 335.0, "y": 235.0, "z": 20.0},
        "zone_id": "zone_alley",
        "zone_name": "Alley Sector",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.87,
        "metadata": {"phase": "tracking", "description": "Alley tracking point — suspect cornered"},
    },
    {
        "waypoint_id": "drone-wp-05",
        "entity_id": "DRONE-ALPHA",
        "entity_type": "drone",
        "offset_seconds": 50,
        "location": {"x": 385.0, "y": 265.0, "z": 22.0},
        "zone_id": "zone_roads",
        "zone_name": "Main Road",
        "source_id": "DRONE-ALPHA",
        "source_type": "drone_camera",
        "confidence": 0.82,
        "metadata": {"phase": "tracking", "description": "Gate/exit route overview — final intercept"},
    },
]


# ---------------------------------------------------------------------------
# Promotion helpers
# ---------------------------------------------------------------------------

def _promotion_record(
    *,
    run_id: str,
    scenario_id: str,
    step: int,
    event_type: str,
    normalized_event: dict[str, Any],
    alert: dict[str, Any] | None,
    incident: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "step": step,
        "event_type": event_type,
        "timestamp": _now_iso(),
        "normalized_event": normalized_event,
        "alert": alert,
        "incident": incident,
    }


def _persist_drone_route(route: "DroneRoute") -> None:
    try:
        _DRONE_ROUTES_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{route.scenario_run_id}_{route.drone_id.lower()}.json"
        path = _DRONE_ROUTES_DIR / filename
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(route.model_dump(mode="json"), default=str))
    except Exception as exc:
        logger.warning("Failed to persist drone route: %s", exc)


def _persist_fused_track(track: "FusedTrack") -> None:
    try:
        _SCENARIO_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        path = _SCENARIO_TRACKING_DIR / f"{track.scenario_run_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(track.model_dump(mode="json"), default=str))
    except Exception as exc:
        logger.warning("Failed to persist fused track: %s", exc)


def _persist_promotion(record: dict[str, Any]) -> None:
    try:
        _PROMOTIONS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = record.get("run_id", "unknown")
        path = _PROMOTIONS_DIR / f"{run_id}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.warning("Failed to persist scenario promotion: %s", exc)


def _build_scenario_alert(
    normalized: dict[str, Any],
    incident_id: str,
    run_id: str,
    scenario_id: str,
) -> dict[str, Any]:
    import time
    ts = time.time()
    alert_id = f"alert-scn-{run_id[:8]}-{normalized.get('event_id', uuid.uuid4().hex[:8])}"
    return {
        "alert_id": alert_id,
        "incident_id": incident_id,
        "event_ids": [normalized.get("event_id")],
        "camera_ids": [normalized["camera_id"]] if normalized.get("camera_id") else [],
        "track_ids": [],
        "identity_ids": [],
        "severity": normalized.get("severity", "medium"),
        "state": "new",
        "title": f"SCENARIO {normalized.get('severity', 'medium').upper()}: {normalized.get('event_type', '').replace('_', ' ')}",
        "description": normalized.get("description", "Scenario observation promoted to alert."),
        "risk_score": float(normalized.get("confidence") or 0.0),
        "confidence": float(normalized.get("confidence") or 0.0),
        "created_at": ts,
        "updated_at": ts,
        "dispatched_at": None,
        "acknowledged_at": None,
        "resolved_at": None,
        "escalation_count": 0,
        "metadata": {
            "source": "scenario_promotion",
            "source_type": "scenario_observation",
            "scenario_id": scenario_id,
            "run_id": run_id,
            "alert_type": normalized.get("event_type"),
            "detected_class": normalized.get("detected_class"),
            "confidence": normalized.get("confidence"),
            "zone": normalized.get("zone"),
            "actor_id": (normalized.get("metadata") or {}).get("actor_id"),
            "camera_id": normalized.get("camera_id"),
            "tracking_view": f"#scenario-tracking/{run_id}",
            "has_tracking_view": True,
        },
    }


def _build_scenario_incident(
    normalized: dict[str, Any],
    run_id: str,
    scenario_id: str,
) -> dict[str, Any]:
    import time
    ts = time.time()
    incident_id = f"inc-scn-{run_id[:8]}-{normalized.get('event_id', uuid.uuid4().hex[:8])}"
    return {
        "incident_id": incident_id,
        "id": incident_id,
        "incident_type": normalized.get("event_type", "scenario_incident"),
        "state": "OPEN",
        "severity": str(normalized.get("severity", "medium")).upper(),
        "confidence": float(normalized.get("confidence") or 0.0),
        "risk_score": float(normalized.get("confidence") or 0.0),
        "camera_ids": [normalized["camera_id"]] if normalized.get("camera_id") else [],
        "track_ids": [],
        "identity_ids": [],
        "events": [normalized],
        "anomalies": [],
        "timeline_refs": [],
        "created_at": ts,
        "updated_at": ts,
        "summary": normalized.get("description", "Scenario observation promoted to incident."),
        "metadata": {
            "source": "scenario_promotion",
            "source_type": "scenario_observation",
            "scenario_id": scenario_id,
            "run_id": run_id,
            "zone": normalized.get("zone"),
        },
    }


# ---------------------------------------------------------------------------
# ScenarioEngineService
# ---------------------------------------------------------------------------

def _build_path_waypoint(raw: dict[str, Any], run_id: str) -> PathWaypoint:
    loc_raw = raw.get("location", {})
    return PathWaypoint(
        waypoint_id=f"{run_id[:8]}-{raw['waypoint_id']}",
        entity_id=raw["entity_id"],
        entity_type=EntityType(raw["entity_type"]),
        offset_seconds=raw["offset_seconds"],
        location=WaypointLocation(**loc_raw),
        zone_id=raw.get("zone_id"),
        zone_name=raw.get("zone_name"),
        source_id=raw.get("source_id"),
        source_type=raw.get("source_type"),
        confidence=raw.get("confidence", 0.85),
        metadata=raw.get("metadata", {}),
    )


def _build_camera_handoff(raw: dict[str, Any], run_id: str) -> CameraHandoff:
    return CameraHandoff(
        handoff_id=f"{run_id[:8]}-{raw['handoff_id']}",
        scenario_run_id=run_id,
        from_camera_id=raw["from_camera_id"],
        to_camera_id=raw["to_camera_id"],
        actor_id=raw["actor_id"],
        offset_seconds=raw["offset_seconds"],
        reason=raw.get("reason", "suspect_movement"),
        confidence=raw.get("confidence", 0.85),
        metadata=raw.get("metadata", {}),
    )


class ScenarioEngineService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_run: ScenarioRun | None = None
        # Per-run tracking state (keyed by run_id)
        self._run_drone_routes: dict[str, DroneRoute] = {}
        self._run_fused_tracks: dict[str, FusedTrack] = {}

    # ------------------------------------------------------------------
    # Catalogue helpers
    # ------------------------------------------------------------------

    def list_scenarios(self) -> list[ScenarioDefinition]:
        return list(SCENARIO_CATALOGUE.values())

    def get_scenario(self, scenario_id: str) -> ScenarioDefinition | None:
        return SCENARIO_CATALOGUE.get(scenario_id)

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    def active_run(self) -> ScenarioRun | None:
        with self._lock:
            return self._active_run

    def active_run_status(self) -> ScenarioRunStatus | None:
        with self._lock:
            return self._active_run.to_status() if self._active_run else None

    def start(self, scenario_id: str, mode: str = "step") -> ScenarioRun:
        with self._lock:
            scenario = SCENARIO_CATALOGUE.get(scenario_id)
            if scenario is None:
                raise ValueError(f"Scenario '{scenario_id}' not found in catalogue")
            if self._active_run and self._active_run.state in {ScenarioState.RUNNING, ScenarioState.PAUSED}:
                raise RuntimeError(
                    f"Cannot start '{scenario_id}': run '{self._active_run.run_id}' "
                    f"is still {self._active_run.state.value}. Cancel or reset first."
                )
            run = ScenarioRun(
                run_id=f"run-{uuid.uuid4().hex[:12]}",
                scenario_id=scenario_id,
                scenario_name=scenario.name,
                state=ScenarioState.RUNNING,
                mode=mode,
                current_step=0,
                total_steps=len(scenario.timeline),
                started_at=_now_iso(),
            )
            self._active_run = run
            logger.info("Scenario run started: %s (mode=%s)", run.run_id, mode)

            if mode == "auto":
                self._auto_run(run, scenario)

            return run

    def step(self) -> dict[str, Any]:
        with self._lock:
            run = self._active_run
            if run is None:
                raise RuntimeError("No active scenario run. Call start() first.")
            if run.state == ScenarioState.PAUSED:
                raise RuntimeError("Run is paused. Call resume() first.")
            if run.state != ScenarioState.RUNNING:
                raise RuntimeError(f"Run is {run.state.value}; cannot step.")

            scenario = SCENARIO_CATALOGUE.get(run.scenario_id)
            if scenario is None:
                raise RuntimeError(f"Scenario '{run.scenario_id}' not found.")

            if run.current_step >= run.total_steps:
                run.state = ScenarioState.COMPLETED
                run.completed_at = _now_iso()
                return {"status": "completed", "run_id": run.run_id, "message": "Scenario already completed."}

            timeline_event = scenario.timeline[run.current_step]
            observation = self._execute_step(run, timeline_event)
            run.current_step += 1

            if run.current_step >= run.total_steps:
                run.state = ScenarioState.COMPLETED
                run.completed_at = _now_iso()

            return {
                "status": "ok",
                "step": timeline_event.step,
                "t_offset_seconds": timeline_event.t_offset_seconds,
                "event_type": timeline_event.event_type,
                "observation": observation,
                "run_status": run.to_status().model_dump(mode="json"),
            }

    def pause(self) -> ScenarioRunStatus:
        with self._lock:
            run = self._active_run
            if run is None:
                raise RuntimeError("No active run to pause.")
            if run.state != ScenarioState.RUNNING:
                raise RuntimeError(f"Run is {run.state.value}; cannot pause.")
            run.state = ScenarioState.PAUSED
            run.paused_at = _now_iso()
            logger.info("Scenario run paused: %s", run.run_id)
            return run.to_status()

    def resume(self) -> ScenarioRunStatus:
        with self._lock:
            run = self._active_run
            if run is None:
                raise RuntimeError("No active run to resume.")
            if run.state != ScenarioState.PAUSED:
                raise RuntimeError(f"Run is {run.state.value}; cannot resume.")
            run.state = ScenarioState.RUNNING
            run.paused_at = None
            logger.info("Scenario run resumed: %s", run.run_id)
            return run.to_status()

    def cancel(self) -> ScenarioRunStatus:
        with self._lock:
            run = self._active_run
            if run is None:
                raise RuntimeError("No active run to cancel.")
            run.state = ScenarioState.CANCELLED
            run.cancelled_at = _now_iso()
            # Advance drone route to CANCELLED
            route = self._run_drone_routes.get(run.run_id)
            if route and route.status not in (DroneRouteStatus.COMPLETED, DroneRouteStatus.CANCELLED):
                route.status = DroneRouteStatus.CANCELLED
                route.updated_at = _now_iso()
                _persist_drone_route(route)
            self._run_fused_tracks.pop(run.run_id, None)
            logger.info("Scenario run cancelled: %s", run.run_id)
            return run.to_status()

    def reset(self) -> None:
        with self._lock:
            if self._active_run:
                logger.info("Scenario run reset: %s", self._active_run.run_id)
            self._active_run = None

    # ------------------------------------------------------------------
    # Observation timeline access
    # ------------------------------------------------------------------

    def run_observation_timeline(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._active_run is None:
                return []
            return list(self._active_run.observation_timeline)

    def list_promotions(self, run_id: str) -> list[dict[str, Any]]:
        path = _PROMOTIONS_DIR / f"{run_id}.jsonl"
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        except Exception as exc:
            logger.warning("Failed to read promotions for run %s: %s", run_id, exc)
        return records

    # ------------------------------------------------------------------
    # Phase 7 — Tracking / Path accessors
    # ------------------------------------------------------------------

    def get_suspect_path(self, run_id: str) -> list[PathWaypoint]:
        """Return deterministic suspect path waypoints for any bank_robbery_demo run."""
        run = self._resolve_run(run_id)
        if run is None or run.scenario_id != "bank_robbery_demo":
            return []
        return [_build_path_waypoint(raw, run_id) for raw in BANK_ROBBERY_SUSPECT_PATH]

    def get_camera_handoffs(self, run_id: str) -> list[CameraHandoff]:
        """Return camera handoff chain for any bank_robbery_demo run."""
        run = self._resolve_run(run_id)
        if run is None or run.scenario_id != "bank_robbery_demo":
            return []
        return [_build_camera_handoff(raw, run_id) for raw in BANK_ROBBERY_CAMERA_HANDOFFS]

    def get_drone_route(self, run_id: str) -> DroneRoute | None:
        """Return DRONE-ALPHA route for a run (exists after drone dispatch step)."""
        with self._lock:
            return self._run_drone_routes.get(run_id)

    def get_fused_track(self, run_id: str) -> FusedTrack | None:
        """Return fused track for a run (built lazily on first request)."""
        with self._lock:
            track = self._run_fused_tracks.get(run_id)
        if track is None:
            run = self._resolve_run(run_id)
            if run is not None:
                track = self._build_fused_track(run)
                with self._lock:
                    self._run_fused_tracks[run_id] = track
                _persist_fused_track(track)
        return track

    def _resolve_run(self, run_id: str) -> ScenarioRun | None:
        with self._lock:
            if self._active_run and self._active_run.run_id == run_id:
                return self._active_run
        return None

    def _create_drone_route(self, run: ScenarioRun, drone_id: str) -> DroneRoute:
        now = _now_iso()
        waypoints = [_build_path_waypoint(raw, run.run_id) for raw in DRONE_ALPHA_ROUTE_WAYPOINTS]
        camera_feed_uri = ""
        try:
            from app.services.simulation_source_service import get_city_surveillance_registry
            reg = get_city_surveillance_registry()
            drone_obj = reg.get_drone(drone_id)
            if drone_obj:
                camera_feed_uri = drone_obj.camera_feed_uri or ""
        except Exception:
            pass
        return DroneRoute(
            route_id=f"route-{run.run_id[:8]}-{drone_id.lower()}",
            scenario_run_id=run.run_id,
            drone_id=drone_id,
            mission_id=f"mission-{run.run_id[:8]}",
            waypoints=waypoints,
            status=DroneRouteStatus.DISPATCHED,
            linked_actor_id="SUSPECT-001",
            created_at=now,
            updated_at=now,
            metadata={
                "scenario_id": run.scenario_id,
                "trigger": "weapon_detected",
                "airsim_ready": False,
                "camera_feed_uri": camera_feed_uri,
            },
        )

    def _build_fused_track(self, run: ScenarioRun) -> FusedTrack:
        now = _now_iso()
        suspect_path = [_build_path_waypoint(raw, run.run_id) for raw in BANK_ROBBERY_SUSPECT_PATH]
        handoffs = [_build_camera_handoff(raw, run.run_id) for raw in BANK_ROBBERY_CAMERA_HANDOFFS]

        cam_obs: list[dict[str, Any]] = []
        drone_obs: list[dict[str, Any]] = []
        for entry in run.observation_timeline:
            obs = entry.get("observation", {})
            src = obs.get("source_type", "")
            if src == "drone_camera":
                drone_obs.append(obs)
            else:
                cam_obs.append(obs)

        promotions = self.list_promotions(run.run_id)
        alert_ids = [p["alert"]["alert_id"] for p in promotions if p.get("alert")]
        incident_ids = [p["incident"]["incident_id"] for p in promotions if p.get("incident")]

        source_types = list(dict.fromkeys(
            ["scenario_observation"]
            + (["drone_camera"] if drone_obs else [])
        ))

        drone_route = self._run_drone_routes.get(run.run_id)
        drone_waypoints: list[PathWaypoint] = drone_route.waypoints if drone_route else []

        all_waypoints = sorted(
            suspect_path + drone_waypoints,
            key=lambda w: w.offset_seconds,
        )

        status = FusedTrackStatus.ACTIVE
        if run.state in {ScenarioState.COMPLETED, ScenarioState.CANCELLED}:
            status = FusedTrackStatus.COMPLETED

        return FusedTrack(
            track_id=f"ftrack-{run.run_id[:8]}",
            scenario_run_id=run.run_id,
            actor_id="SUSPECT-001",
            source_types=source_types,
            waypoints=all_waypoints,
            camera_observations=cam_obs,
            drone_observations=drone_obs,
            handoffs=handoffs,
            alert_ids=alert_ids,
            incident_ids=incident_ids,
            confidence=0.88,
            status=status,
            created_at=now,
            updated_at=now,
            metadata={"scenario_id": run.scenario_id, "run_id": run.run_id},
        )

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _execute_step(self, run: ScenarioRun, te: ScenarioTimelineEvent) -> dict[str, Any]:
        try:
            from app.services.command_center_intelligence_service import CommandCenterIntelligenceService
            from app.services.simulation_source_service import get_city_surveillance_registry
        except Exception as exc:
            logger.warning("Scenario step imports failed: %s", exc)
            return {"error": str(exc)}

        source_meta: dict[str, Any] = {"simulated": True, "scenario_id": run.scenario_id, "run_id": run.run_id}
        try:
            registry = get_city_surveillance_registry()
            if te.camera_id:
                cam_meta = registry.source_metadata(camera_id=te.camera_id)
                source_meta.update(cam_meta)
                registry.mark_observation(te.camera_id)
            if te.drone_id:
                drone_meta = registry.source_metadata(drone_id=te.drone_id)
                source_meta.update(drone_meta)
        except Exception as exc:
            logger.warning("Source metadata lookup failed at step %d: %s", te.step, exc)

        obs_source_type = "scenario_observation"
        if te.drone_id and not te.camera_id:
            obs_source_type = "drone_camera"

        obs_dict: dict[str, Any] = {
            "source_type": obs_source_type,
            "scenario_id": run.scenario_id,
            "run_id": run.run_id,
            "camera_id": te.camera_id,
            "drone_id": te.drone_id,
            "zone": te.zone_id,
            "event_type": te.event_type,
            "confidence": te.confidence,
            "severity": te.severity,
            "description": te.description,
            "timestamp": _now_iso(),
            "detected_class": te.detected_class,
            "metadata": {
                **source_meta,
                **te.metadata,
                "step": te.step,
                "t_offset_seconds": te.t_offset_seconds,
                "actor_id": te.actor_id,
            },
        }

        try:
            service = CommandCenterIntelligenceService()
            normalized = service.simulation_adapter.normalize_observation(obs_dict)
            normalized_dict = normalized.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Normalization failed at step %d: %s", te.step, exc)
            normalized_dict = obs_dict

        run.observations_generated += 1
        run.observation_timeline.append({
            "step": te.step,
            "t_offset_seconds": te.t_offset_seconds,
            "event_type": te.event_type,
            "observation": normalized_dict,
        })

        alert_dict: dict[str, Any] | None = None
        incident_dict: dict[str, Any] | None = None

        if te.promote_to_alert or te.promote_to_incident:
            incident_dict = _build_scenario_incident(normalized_dict, run.run_id, run.scenario_id)
            alert_dict = _build_scenario_alert(normalized_dict, incident_dict["incident_id"], run.run_id, run.scenario_id)
            incident_dict.setdefault("metadata", {})["alert_id"] = alert_dict["alert_id"]
            if te.promote_to_alert:
                run.alerts_promoted += 1
            if te.promote_to_incident:
                run.incidents_promoted += 1
            promo = _promotion_record(
                run_id=run.run_id,
                scenario_id=run.scenario_id,
                step=te.step,
                event_type=te.event_type,
                normalized_event=normalized_dict,
                alert=alert_dict,
                incident=incident_dict,
            )
            _persist_promotion(promo)

        if te.trigger_drone_dispatch and not run.drone_dispatched:
            dispatch_drone_id = "DRONE-ALPHA"
            try:
                from app.models.simulation_source_models import SimDroneStatus
                registry = get_city_surveillance_registry()
                registry.update_drone_status(
                    dispatch_drone_id,
                    SimDroneStatus.MISSION,
                    reason=f"scenario dispatch: {run.run_id}",
                )
                run.drone_dispatched = True
                run.dispatched_drone_id = dispatch_drone_id
                route = self._create_drone_route(run, dispatch_drone_id)
                self._run_drone_routes[run.run_id] = route
                _persist_drone_route(route)
                # Invalidate cached fused track so it rebuilds with drone route
                self._run_fused_tracks.pop(run.run_id, None)
                logger.info("DRONE-ALPHA dispatched + route created for run %s", run.run_id)
            except Exception as exc:
                logger.warning("Drone dispatch failed: %s", exc)

        # Advance drone route status based on event type
        route = self._run_drone_routes.get(run.run_id)
        if route:
            if te.event_type == "drone_observation" and route.status == DroneRouteStatus.DISPATCHED:
                route.status = DroneRouteStatus.TRACKING
                route.updated_at = _now_iso()
                _persist_drone_route(route)
                logger.debug("DroneRoute %s advanced to TRACKING", route.route_id)
            elif te.event_type == "scenario_incident" and route.status in (
                DroneRouteStatus.DISPATCHED, DroneRouteStatus.TRACKING
            ):
                route.status = DroneRouteStatus.COMPLETED
                route.updated_at = _now_iso()
                _persist_drone_route(route)
                logger.debug("DroneRoute %s advanced to COMPLETED", route.route_id)

        # If run just completed, also mark route completed and persist fused track
        if run.current_step + 1 >= run.total_steps:
            if route and route.status == DroneRouteStatus.TRACKING:
                route.status = DroneRouteStatus.COMPLETED
                route.updated_at = _now_iso()
                _persist_drone_route(route)

        # Invalidate fused track cache after each step so it stays current
        self._run_fused_tracks.pop(run.run_id, None)
        return normalized_dict

    def _auto_run(self, run: ScenarioRun, scenario: ScenarioDefinition) -> None:
        for i in range(len(scenario.timeline)):
            if run.state != ScenarioState.RUNNING:
                break
            te = scenario.timeline[i]
            self._execute_step(run, te)
            run.current_step = i + 1

        if run.state == ScenarioState.RUNNING:
            run.state = ScenarioState.COMPLETED
            run.completed_at = _now_iso()
            logger.info("Auto-run completed: %s", run.run_id)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: ScenarioEngineService | None = None
_engine_lock = threading.Lock()


def get_scenario_engine() -> ScenarioEngineService:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ScenarioEngineService()
    return _engine
