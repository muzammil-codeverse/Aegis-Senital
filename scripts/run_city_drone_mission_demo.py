#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models.drone_fusion_models import FusionObservation, FusionSourceRef
from app.models.drone_mission_models import DroneMissionCreateRequest, DroneMissionSession
from app.repositories.drone_fusion_repository import get_drone_fusion_repository
from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.services.case_service import get_case_service
from app.services.drone.drone_mission_evidence_service import get_drone_mission_evidence_service
from app.services.drone.drone_mission_execution_service import get_drone_mission_execution_service
from app.services.drone.drone_mission_service import get_drone_mission_service
from app.services.drone.drone_simulation_service import DroneSimulationService
from app.services.drone.drone_frame_adapter import DroneFrameAdapter
from inference.model_pool import get_model_pool
from inference.stream.stream_processor import StreamProcessor
from ml.runtime import ModelRouter, system_boot_check


def _run_python(script_path: Path, *args: str, debug: bool = False) -> int:
    command = [sys.executable, str(script_path), *args]
    completed = subprocess.run(command, check=False, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if debug:
        print(f"[debug] command={' '.join(command)}")
        print(completed.stdout)
    return completed.returncode


def _load_mission_config() -> dict[str, Any]:
    path = ROOT / "configs" / "runtime" / "drone_city_missions.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(payload.get("drone_city_missions") or {})


def _mission_by_name(name: str) -> dict[str, Any]:
    for item in _load_mission_config().get("presets") or []:
        if str(item.get("name")) == name:
            return dict(item)
    raise KeyError(name)


def _route_key_for_runtime(runtime_name: str) -> str:
    key = str(runtime_name or "").strip()
    if key == "CityEnviron":
        return "city_route"
    if key == "AirSimNH":
        return "neighborhood_route"
    return "compact_route"


def _points_for_runtime(preset: dict[str, Any], runtime_name: str) -> list[dict[str, Any]]:
    routes = dict(preset.get("routes") or {})
    route_key = _route_key_for_runtime(runtime_name)
    points = list(routes.get(route_key) or [])
    if points:
        return points
    # backward compatibility with previous shape
    legacy = list(preset.get("waypoints") or [])
    return legacy


def _process_frame_with_stream_processor(frame_packet: Any, device: str) -> dict[str, Any]:
    pool = get_model_pool()
    if not pool.is_loaded:
        system_boot_check()
        router = ModelRouter()
        weapon = router.get_model("weapon")
        phone = router.get_model("phone")
        pool.load(weapon_path=weapon["resolved_path"], phone_path=phone["resolved_path"], device=device)
    processor = StreamProcessor(
        stream_id=f"cam_{frame_packet.camera_id}",
        source=f"cosys_airsim://{frame_packet.camera_id}",
        model_pool=pool,
    )
    processor.source_type = "drone_simulation"
    return processor.process_decoded_packet(frame_packet)


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# City Drone Mission Demo Report",
        "",
        f"- Mission: `{payload.get('mission_name')}`",
        f"- Runtime: `{payload.get('runtime_name')}`",
        f"- Session ID: `{payload.get('session_id')}`",
        "- Safety label: Simulated drone feed",
        "- Safety label: Operator review required",
        "",
        "## Outcome",
        f"- Mission status: `{payload.get('mission_status')}`",
        f"- Underlying execution status: `{payload.get('execution_status')}`",
        f"- Telemetry points: `{payload.get('telemetry_points')}`",
        f"- Frames processed: `{payload.get('frames_processed')}`",
        f"- Detections observed: `{payload.get('detections')}`",
        "",
        "## Notes",
        "- Simulated aerial observation",
        "- Candidate cross-source observation",
        "- Possible movement path",
        "- Evidence-backed hypothesis",
        "- Insufficient data (when confidence is low)",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _final_mission_status(runtime_name: str, execution_status: str, had_frame: bool, had_telemetry: bool) -> tuple[str, str | None]:
    if runtime_name == "Blocks":
        if execution_status == "completed":
            return "completed_fallback", None
        if execution_status in {"failed", "cancelled"} and had_frame and had_telemetry:
            return "degraded_fallback_complete", "Blocks movement constraints prevented full route completion; telemetry/frame evidence collected."
    if execution_status == "completed":
        return "completed", None
    if execution_status in {"failed", "cancelled"} and had_frame and had_telemetry:
        return "completed_with_warnings", "Mission ended early but captured sufficient simulated observation evidence."
    return execution_status, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a city drone mission demo against selected runtime.")
    parser.add_argument("--mission", default="fixed_camera_handoff_demo")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--prefer", default="AirSimNH", choices=["AirSimNH", "CityEnviron", "Blocks"])
    parser.add_argument("--runtime", choices=["AirSimNH", "CityEnviron", "Blocks"], default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--with-case", action="store_true")
    args = parser.parse_args()

    preset = _mission_by_name(args.mission)
    target_runtime = args.runtime or args.prefer

    _run_python(ROOT / "scripts" / "configure_drone_multicamera_settings.py", "--profile", "city_demo", debug=args.debug)
    launch_args = ["--prefer", target_runtime, "--fallback", "AirSimNH", "--windowed", "--res", "960x540"]
    if args.debug:
        launch_args.extend(["--kill-stale"])
    _run_python(ROOT / "scripts" / "launch_city_drone_runtime.py", *launch_args, debug=args.debug)

    simulation_service = DroneSimulationService()
    status = simulation_service.connect()
    if not status.connected:
        print(json.dumps({"status": "failed", "reason": status.last_error or "Unable to connect runtime"}, indent=2))
        return 1

    runtime_name = simulation_service.get_runtime_status().selected_runtime or target_runtime
    points = _points_for_runtime(preset, runtime_name)
    if not points:
        print(json.dumps({"status": "failed", "reason": f"No route points found for runtime {runtime_name}"}, indent=2))
        return 1

    mission_request = DroneMissionCreateRequest.model_validate(
        {
            "name": f"City demo mission: {preset.get('name')}",
            "description": preset.get("description"),
            "route_type": "linear",
            "waypoints": [
                {
                    "sequence_index": idx,
                    "latitude": float(point["lat"]),
                    "longitude": float(point["lon"]),
                    "altitude_meters": float(point.get("altitude_m") or 40),
                    "velocity_mps": float(point.get("velocity_mps") or 4.0),
                    "hold_seconds": float(point.get("hold_seconds") or preset.get("dwell_seconds") or 2),
                    "camera_action": "hover_and_observe",
                    "metadata": {
                        "action": point.get("action"),
                        "simulated": True,
                        "operator_review_required": True,
                        "demo": True,
                    },
                }
                for idx, point in enumerate(points)
            ],
            "metadata": {
                "demo": True,
                "simulated": True,
                "operator_review_required": True,
                "target_runtime": target_runtime,
                "selected_runtime": runtime_name,
                "safe_wording": preset.get("safe_wording"),
                "expected_demo_outcome": preset.get("expected_demo_outcome"),
            },
        }
    )

    mission_service = get_drone_mission_service()
    mission = mission_service.create_mission(mission_request, created_by="operator")

    repo = get_drone_mission_repository()
    execution_service = get_drone_mission_execution_service()
    session = DroneMissionSession(
        mission_id=mission.mission_id,
        drone_id=mission.assigned_drone_id,
        total_waypoints=len(mission.waypoints),
        started_by="operator",
    )
    repo.start_session(session)
    session = execution_service.start_mission(mission, session, started_by="operator")

    completed = execution_service.execute_mission_sync(mission, session.session_id)
    if completed is None:
        print(json.dumps({"status": "failed", "reason": "Mission execution returned no session result"}, indent=2))
        return 1

    selected_camera = str(preset.get("camera") or "front_center").strip().lower()
    frames = simulation_service.get_multi_camera_frames([selected_camera, "front_center"])
    frames = [frame for frame in frames if frame.frame_available]
    telemetry = simulation_service.get_telemetry()
    had_telemetry = telemetry.status == "connected"
    had_frame = bool(frames)

    processing = {"events": [], "anomalies": [], "incidents": []}
    if frames:
        decoded = DroneFrameAdapter.to_decoded_packet(
            frames[0],
            frames[0].telemetry,
            mission_id=mission.mission_id,
            session_id=completed.session_id,
            city_runtime=runtime_name,
        )
        processing = _process_frame_with_stream_processor(decoded, args.device)

    detection_events = repo.list_events(session_id=completed.session_id, limit=500)

    fusion_created = False
    fusion_observation_id = None
    if frames and frames[0].telemetry:
        observation = FusionObservation(
            source_type="drone_simulation",
            source_id=frames[0].source_id or f"{frames[0].drone_id}_{frames[0].camera_name}",
            event_id=completed.session_id,
            case_id=None,
            timestamp=frames[0].timestamp,
            latitude=frames[0].telemetry.latitude,
            longitude=frames[0].telemetry.longitude,
            altitude_meters=frames[0].telemetry.altitude_meters,
            geo_missing=frames[0].telemetry.latitude is None or frames[0].telemetry.longitude is None,
            event_type="candidate_cross_source_observation",
            severity="medium",
            simulated=True,
            source_ref=FusionSourceRef(
                source_type="drone_simulation",
                source_id=frames[0].source_id or f"{frames[0].drone_id}_{frames[0].camera_name}",
                event_id=completed.session_id,
                simulated=True,
            ),
            metadata={
                "mission_id": mission.mission_id,
                "session_id": completed.session_id,
                "city_runtime": runtime_name,
                "safe_label": "Candidate cross-source observation",
                "operator_review_required": True,
                "demo": True,
            },
        )
        saved = get_drone_fusion_repository().save_observation(observation)
        fusion_created = True
        fusion_observation_id = saved.observation_id

    case_id = None
    evidence_attached = False
    if args.with_case:
        case_service = get_case_service()
        case = case_service.create_case(
            {
                "title": "Demo scenario: simulated drone mission handoff",
                "description": "Evidence-backed hypothesis from simulated aerial observation. Operator review required.",
                "priority": "medium",
                "severity": "medium",
                "camera_ids": [simulation_service.drone_id],
                "source_event_ids": [completed.session_id],
                "requires_review": True,
                "review_status": "pending",
                "metadata": {
                    "demo": True,
                    "simulated": True,
                    "operator_review_required": True,
                    "city_runtime": runtime_name,
                },
            },
            actor="operator",
        )
        case_id = case.case_id
        get_drone_mission_evidence_service().attach_bundle_to_case(
            case.case_id,
            completed.session_id,
            actor="operator",
            selected_frame_snapshots=[],
            detection_summary={
                "events": len(processing.get("events") or []),
                "anomalies": len(processing.get("anomalies") or []),
                "incidents": len(processing.get("incidents") or []),
            },
            fusion_summary={
                "fusion_observation_created": fusion_created,
                "fusion_observation_id": fusion_observation_id,
            },
        )
        evidence_attached = True

    execution_status = str(completed.status.value)
    mission_status, mission_reason = _final_mission_status(runtime_name, execution_status, had_frame, had_telemetry)

    report_payload = {
        "mission_name": args.mission,
        "runtime_name": runtime_name,
        "session_id": completed.session_id,
        "simulated": True,
        "execution_status": execution_status,
        "mission_status": mission_status,
        "mission_status_reason": mission_reason,
        "telemetry_points": completed.telemetry_count,
        "mission_events": len(detection_events),
        "frames_processed": 1 if frames else 0,
        "detections": len(processing.get("events") or []),
        "fusion_observation_created": fusion_created,
        "fusion_observation_id": fusion_observation_id,
        "case_id": case_id,
        "evidence_attached": evidence_attached,
    }

    report_path = ROOT / "storage" / "drone_sim" / "city_mission_demo_report.md"
    _write_report(report_path, report_payload)
    print(json.dumps({**report_payload, "report_path": str(report_path.resolve())}, indent=2))

    if mission_status in {"failed", "cancelled"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
