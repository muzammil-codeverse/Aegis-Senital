#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models.case_models import CaseEvidence
from app.models.drone_fusion_models import (
    CrossSourceCorrelation,
    DroneCameraHandoff,
    FusionConfidenceBreakdown,
    FusionObservation,
    FusionSourceRef,
)
from app.models.drone_mission_models import DroneMissionCreateRequest
from app.models.gis_models import CameraGeoProfile, GeoFenceZone, GeoPoint
from app.models.incident_models import IncidentEventRecord
from app.models.investigation_models import InvestigationSubjectRef, PathConfidenceBreakdown, PathHypothesis, PathHypothesisStep
from app.repositories.drone_fusion_repository import get_drone_fusion_repository
from app.repositories.gis_repository import get_gis_repository, new_zone_id
from app.repositories.incident_repository import get_incident_repository
from app.repositories.investigation_repository import get_investigation_repository
from app.services.case_service import get_case_service
from app.services.drone.drone_mission_service import get_drone_mission_service


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _cleanup_demo_rows() -> None:
    targets = [
        ROOT / "storage" / "gis" / "camera_geo_profiles.jsonl",
        ROOT / "storage" / "gis" / "geofences.jsonl",
        ROOT / "storage" / "drone_missions" / "missions.jsonl",
        ROOT / "storage" / "drone_missions" / "sessions.jsonl",
        ROOT / "storage" / "drone_missions" / "telemetry.jsonl",
        ROOT / "storage" / "drone_missions" / "events.jsonl",
        ROOT / "storage" / "drone_missions" / "reports.jsonl",
        ROOT / "storage" / "drone_fusion" / "observations.jsonl",
        ROOT / "storage" / "drone_fusion" / "correlations.jsonl",
        ROOT / "storage" / "drone_fusion" / "handoffs.jsonl",
        ROOT / "storage" / "investigation" / "hypotheses.jsonl",
    ]
    for target in targets:
        rows = _read_jsonl(target)
        cleaned = [row for row in rows if not bool((row.get("metadata") or {}).get("demo"))]
        _write_jsonl(target, cleaned)

    incidents_dir = ROOT / "storage" / "incidents"
    for path in incidents_dir.glob("incident_events_*.jsonl"):
        rows = _read_jsonl(path)
        cleaned = [row for row in rows if not bool((row.get("metadata") or {}).get("demo"))]
        _write_jsonl(path, cleaned)

    case_service = get_case_service()
    for case in case_service.list_cases({"limit": 2000}):
        if bool((case.metadata or {}).get("demo")):
            try:
                case_service.archive_case(case.case_id, actor="system", reason="Reset demo-only dataset")
            except Exception:
                continue


def _seed_camera_profiles(center_lat: float, center_lon: float) -> list[str]:
    repo = get_gis_repository()
    offsets = [
        (0.0000, 0.0000),
        (0.0010, 0.0008),
        (-0.0009, 0.0011),
        (0.0013, -0.0010),
        (-0.0012, -0.0008),
    ]
    camera_ids: list[str] = []
    for index, (d_lat, d_lon) in enumerate(offsets, start=1):
        camera_id = f"camera_{index:02d}"
        camera_ids.append(camera_id)
        repo.upsert_camera_geo_profile(
            CameraGeoProfile(
                camera_id=camera_id,
                name=f"Demo Camera {index:02d}",
                latitude=center_lat + d_lat,
                longitude=center_lon + d_lon,
                heading_degrees=45.0 * index,
                fov_degrees=80.0,
                coverage_radius_meters=140.0,
                region="multan_demo_grid",
                metadata={
                    "demo": True,
                    "simulated": True,
                    "operator_review_required": True,
                    "source_type": "live_stream",
                },
            )
        )
    return camera_ids


def _seed_geofence(center_lat: float, center_lon: float) -> str:
    repo = get_gis_repository()
    zone = GeoFenceZone(
        zone_id=new_zone_id(),
        name="Demo Geofence Zone",
        zone_type="patrol",
        severity="medium",
        active=True,
        polygon=[
            GeoPoint(latitude=center_lat - 0.0018, longitude=center_lon - 0.0018),
            GeoPoint(latitude=center_lat - 0.0018, longitude=center_lon + 0.0018),
            GeoPoint(latitude=center_lat + 0.0018, longitude=center_lon + 0.0018),
            GeoPoint(latitude=center_lat + 0.0018, longitude=center_lon - 0.0018),
        ],
        metadata={"demo": True, "simulated": True, "operator_review_required": True},
    )
    repo.create_geofence(zone)
    return zone.zone_id


def _seed_demo_incident(camera_id: str, center_lat: float, center_lon: float) -> IncidentEventRecord:
    incident_repo = get_incident_repository()
    incident_id = f"demo_inc_{uuid.uuid4().hex[:10]}"
    record = IncidentEventRecord(
        incident_id=incident_id,
        event_id=incident_id,
        source_type="live_stream",
        camera_id=camera_id,
        session_id=camera_id,
        case_id=None,
        event_type="possible_incident",
        severity="medium",
        risk_score=0.54,
        timestamp=_now_iso(),
        summary="Demo scenario possible incident. Operator review required.",
        metadata={
            "demo": True,
            "simulated": True,
            "operator_review_required": True,
            "latitude": center_lat + 0.0002,
            "longitude": center_lon + 0.0003,
            "safe_label": "Possible incident",
            "analytics_category": "demo_scenario",
        },
    )
    return incident_repo.append_event(record)


def _seed_demo_mission(center_lat: float, center_lon: float) -> str:
    mission_service = get_drone_mission_service()
    request = DroneMissionCreateRequest.model_validate(
        {
            "name": "Demo scenario mission route",
            "description": "Simulated drone mission route for city dashboard demo.",
            "route_type": "linear",
            "waypoints": [
                {
                    "sequence_index": 0,
                    "latitude": center_lat,
                    "longitude": center_lon,
                    "altitude_meters": 45,
                    "velocity_mps": 4,
                    "hold_seconds": 2,
                    "camera_action": "hover_and_observe",
                    "metadata": {"demo": True, "simulated": True, "operator_review_required": True},
                },
                {
                    "sequence_index": 1,
                    "latitude": center_lat + 0.0007,
                    "longitude": center_lon + 0.0007,
                    "altitude_meters": 45,
                    "velocity_mps": 4,
                    "hold_seconds": 2,
                    "camera_action": "hover_and_observe",
                    "metadata": {"demo": True, "simulated": True, "operator_review_required": True},
                },
                {
                    "sequence_index": 2,
                    "latitude": center_lat + 0.0011,
                    "longitude": center_lon + 0.0012,
                    "altitude_meters": 45,
                    "velocity_mps": 4,
                    "hold_seconds": 2,
                    "camera_action": "hover_and_observe",
                    "metadata": {"demo": True, "simulated": True, "operator_review_required": True},
                },
            ],
            "metadata": {
                "demo": True,
                "simulated": True,
                "operator_review_required": True,
                "model_governance": {
                    "weapon_detector": "active",
                    "phone_detector": "active",
                    "anomaly_adapter": "active",
                },
            },
        }
    )
    mission = mission_service.create_mission(request, created_by="operator")
    return mission.mission_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed city-scale drone demo scenario data.")
    parser.add_argument("--reset-demo-only", action="store_true")
    parser.add_argument("--city", default="multan")
    args = parser.parse_args()

    if args.reset_demo_only:
        _cleanup_demo_rows()

    center = {"multan": (30.1575, 71.5249)}
    center_lat, center_lon = center.get(args.city.lower(), center["multan"])

    camera_ids = _seed_camera_profiles(center_lat, center_lon)
    zone_id = _seed_geofence(center_lat, center_lon)
    incident = _seed_demo_incident(camera_ids[0], center_lat, center_lon)
    mission_id = _seed_demo_mission(center_lat, center_lon)

    fusion_repo = get_drone_fusion_repository()
    fixed_obs = fusion_repo.save_observation(
        FusionObservation(
            source_type="fixed_camera",
            source_id=camera_ids[0],
            event_id=incident.event_id,
            case_id=None,
            timestamp=_now_iso(),
            latitude=center_lat + 0.00025,
            longitude=center_lon + 0.00035,
            geo_missing=False,
            event_type="candidate_cross_source_observation",
            severity="medium",
            simulated=True,
            source_ref=FusionSourceRef(source_type="fixed_camera", source_id=camera_ids[0], event_id=incident.event_id, simulated=True),
            metadata={"demo": True, "simulated": True, "operator_review_required": True},
        )
    )
    drone_obs = fusion_repo.save_observation(
        FusionObservation(
            source_type="drone_simulation",
            source_id="drone_sim_01_front_center",
            event_id=incident.event_id,
            case_id=None,
            timestamp=_now_iso(),
            latitude=center_lat + 0.0005,
            longitude=center_lon + 0.0004,
            altitude_meters=45.0,
            geo_missing=False,
            event_type="candidate_cross_source_observation",
            severity="medium",
            simulated=True,
            source_ref=FusionSourceRef(source_type="drone_simulation", source_id="drone_sim_01_front_center", event_id=incident.event_id, simulated=True),
            metadata={"demo": True, "simulated": True, "operator_review_required": True},
        )
    )

    correlation = fusion_repo.save_correlation(
        CrossSourceCorrelation(
            primary_observation_id=fixed_obs.observation_id,
            matched_observation_id=drone_obs.observation_id,
            source_pair=["fixed_camera", "drone_simulation"],
            confidence=0.67,
            confidence_breakdown=FusionConfidenceBreakdown(
                time_score=0.7,
                geo_score=0.68,
                appearance_score=0.0,
                event_type_score=0.64,
                mission_context_score=0.7,
                weighted_total=0.67,
            ),
            safe_summary="Candidate cross-source observation between simulated aerial observation and fixed camera.",
            operator_review_required=True,
            review_status="pending",
            case_id=None,
            event_id=incident.event_id,
            evidence_refs=[incident.event_id],
        )
    )

    handoff = fusion_repo.save_handoff(
        DroneCameraHandoff(
            from_source_type="drone_simulation",
            from_source_id="drone_sim_01_front_center",
            to_source_type="fixed_camera",
            to_source_id=camera_ids[0],
            reason="candidate fixed-camera handoff near demo incident",
            confidence=0.67,
            safe_summary="Possible movement path between simulated aerial observation and nearby fixed camera.",
            case_id=None,
            event_id=incident.event_id,
            evidence_refs=[incident.event_id],
            operator_review_required=True,
        )
    )

    investigation_repo = get_investigation_repository()
    hypothesis = investigation_repo.save_hypothesis(
        PathHypothesis(
            hypothesis_id=f"hyp_{uuid.uuid4().hex[:10]}",
            case_id=None,
            subject_ref=InvestigationSubjectRef(type="event", ref_id=incident.event_id, display_label="Demo scenario subject"),
            start_event_id=incident.event_id,
            steps=[
                PathHypothesisStep(
                    step_index=0,
                    step_type="drone_observation",
                    source_id="drone_sim_01_front_center",
                    source_type="drone_simulation",
                    camera_id="drone_sim_01_front_center",
                    camera_name="Simulated Drone Feed",
                    latitude=center_lat + 0.0005,
                    longitude=center_lon + 0.0004,
                    altitude_meters=45.0,
                    timestamp=_now_iso(),
                    event_id=incident.event_id,
                    step_confidence=0.62,
                    safe_label="Simulated aerial observation",
                    evidence_refs=[incident.event_id],
                ),
                PathHypothesisStep(
                    step_index=1,
                    step_type="fixed_camera",
                    source_id=camera_ids[0],
                    source_type="fixed_camera",
                    camera_id=camera_ids[0],
                    camera_name="Demo Camera 01",
                    latitude=center_lat + 0.0002,
                    longitude=center_lon + 0.0003,
                    timestamp=_now_iso(),
                    event_id=incident.event_id,
                    step_confidence=0.59,
                    safe_label="Possible movement path",
                    evidence_refs=[incident.event_id],
                ),
            ],
            confidence=0.61,
            confidence_breakdown=PathConfidenceBreakdown(time_consistency=0.62, geo_distance=0.63, travel_feasibility=0.58),
            review_status="pending",
            operator_review_required=True,
            safe_summary="Evidence-backed hypothesis for possible movement path in demo scenario.",
            created_at=_now_iso(),
            evidence_refs=[incident.event_id],
            metadata={"demo": True, "simulated": True, "operator_review_required": True},
        )
    )

    case_service = get_case_service()
    case = case_service.create_case(
        {
            "title": "Demo scenario: simulated drone and fixed-camera handoff",
            "description": "Evidence-backed hypothesis from simulated aerial observation and fixed camera proximity.",
            "priority": "medium",
            "severity": "medium",
            "camera_ids": [camera_ids[0], "drone_sim_01_front_center"],
            "source_event_ids": [incident.event_id],
            "requires_review": True,
            "review_status": "pending",
            "metadata": {
                "demo": True,
                "simulated": True,
                "operator_review_required": True,
                "mission_id": mission_id,
                "fusion_observation_id": drone_obs.observation_id,
                "correlation_id": correlation.correlation_id,
                "handoff_id": handoff.handoff_id,
                "investigation_hypothesis_id": hypothesis.hypothesis_id,
            },
        },
        actor="operator",
    )

    evidence = case_service.store_evidence(
        CaseEvidence(
            case_id=case.case_id,
            evidence_type="system_report",
            title="Demo mission evidence placeholder",
            description="Demo scenario simulated evidence placeholder. Operator review required.",
            source_event_id=incident.event_id,
            metadata={"demo": True, "simulated": True, "operator_review_required": True},
        ),
        actor="operator",
    )

    payload = {
        "status": "ok",
        "city": args.city,
        "demo": True,
        "simulated": True,
        "operator_review_required": True,
        "camera_ids": camera_ids,
        "geofence_zone_id": zone_id,
        "incident_id": incident.event_id,
        "mission_id": mission_id,
        "fusion_observation_id": drone_obs.observation_id,
        "fusion_correlation_id": correlation.correlation_id,
        "handoff_id": handoff.handoff_id,
        "investigation_hypothesis_id": hypothesis.hypothesis_id,
        "case_id": case.case_id,
        "evidence_id": evidence.evidence_id,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
