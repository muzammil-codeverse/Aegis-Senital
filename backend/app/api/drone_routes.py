from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from app.api.object_authorization import can_access_camera, ensure_stream_access
from app.api.security_dependencies import (
    get_current_user_from_request,
    require_permission as require_api_permission,
)
from app.api.websocket_security import authenticate_websocket, reject_ws
from app.models.drone_simulation_models import DroneCommandRequest
from app.models.security_models import AuditAction, UserAccount
from app.security.config import get_rbac_config
from app.security.permissions import has_permission
from app.services.audit_log_service import get_audit_log_service
from app.services.drone.drone_camera_registry import SUPPORTED_DRONE_CAMERAS, build_drone_source_id
from app.repositories.drone_fusion_repository import get_drone_fusion_repository
from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.repositories.incident_repository import get_incident_repository
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager

router = APIRouter(tags=["drone-simulation"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(
    request: Request | WebSocket,
    action: AuditAction,
    *,
    user: UserAccount | None,
    resource_id: str,
    success: bool = True,
    detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        get_audit_log_service().record(
            action,
            user=user,
            resource_type="drone_simulation",
            resource_id=resource_id,
            success=success,
            detail=detail,
            request=request,
            metadata=metadata,
        )
    except Exception:
        pass


def _require_stream_capability(user: UserAccount, permission: str) -> None:
    if not has_permission(user.role, permission, get_rbac_config()):
        raise HTTPException(status_code=403, detail=f"{permission} permission is required")


def _service_drone_id() -> str:
    return get_drone_simulation_service().drone_id


def _service_camera_names(service) -> list[str]:
    cameras = getattr(service, "allowed_cameras", None)
    if cameras is None:
        return ["front_center"]
    return [str(item).strip().lower() for item in cameras if str(item).strip()]


def _sensitive_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }


def _ws_payload(message_type: str, data: dict | None = None) -> dict:
    return {
        "type": message_type,
        "source_type": "drone_simulation",
        "simulated": True,
        "operator_review_required": True,
        "timestamp": _now_iso(),
        "data": data or {},
    }


def _require_drone_read(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("drone:read")),
) -> UserAccount:
    _require_stream_capability(current_user, "stream:read")
    ensure_stream_access(request, current_user, _service_drone_id())
    return current_user


def _require_drone_control(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("drone:control")),
) -> UserAccount:
    _require_stream_capability(current_user, "stream:write")
    ensure_stream_access(request, current_user, _service_drone_id())
    return current_user


@router.get("/api/drone-simulation/status")
def get_drone_simulation_status_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    manager = get_drone_simulation_session_manager()
    service = get_drone_simulation_service()
    session = manager.get_session_status()
    telemetry = manager.get_latest_telemetry() or service.latest_telemetry()
    frame = manager.get_latest_frame() or service.latest_frame()
    health = service.get_health(active_session=bool(session.active))
    runtime_status = service.get_runtime_status() if hasattr(service, "get_runtime_status") else {
        "selected_runtime": None,
        "available_runtimes": [],
        "fallback_used": False,
        "connected": bool(getattr(health, "simulator_connected", False)),
        "port_open": False,
    }
    connection = service.connect() if not session.active and telemetry is None else {
        "drone_id": service.drone_id,
        "provider": "cosys_airsim",
        "status": "connected" if health.simulator_connected else ("degraded" if health.status == "degraded" else "disconnected"),
        "connected": bool(health.simulator_connected),
        "camera_name": service.config.get("connection", {}).get("camera_name"),
        "vehicle_name": service.config.get("connection", {}).get("vehicle_name"),
        "last_error": health.last_error,
        "checked_at": _now_iso(),
    }
    return {
        "item": {
            "session": session.model_dump(mode="json"),
            "connection": connection.model_dump(mode="json") if hasattr(connection, "model_dump") else connection,
            "health": health.model_dump(mode="json"),
            "runtime_status": runtime_status.model_dump(mode="json") if hasattr(runtime_status, "model_dump") else runtime_status,
            "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else None,
            "latest_frame_available": bool(frame and frame.frame_available),
            "camera_sources": [
                {
                    "source_id": build_drone_source_id(service.drone_id, camera_name),
                    "camera_name": camera_name,
                    "source_type": "drone_simulation",
                    "drone_id": service.drone_id,
                    "simulated": True,
                    "operator_review_required": True,
                }
                for camera_name in _service_camera_names(service)
            ],
        },
        "status": "ok",
    }


@router.post("/api/drone-simulation/start")
def start_drone_simulation_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    session = get_drone_simulation_session_manager().start_session(current_user)
    _audit(
        request,
        AuditAction.DRONE_SIMULATION_STARTED,
        user=get_current_user_from_request(request),
        resource_id=session.session_id,
        detail="Simulated drone session started",
    )
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.post("/api/drone-simulation/stop")
def stop_drone_simulation_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    session = get_drone_simulation_session_manager().stop_session(current_user)
    _audit(
        request,
        AuditAction.DRONE_SIMULATION_STOPPED,
        user=get_current_user_from_request(request),
        resource_id=session.session_id,
        detail="Simulated drone session stopped",
    )
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.get("/api/drone-simulation/telemetry")
def get_drone_simulation_telemetry_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    manager = get_drone_simulation_session_manager()
    telemetry = manager.get_latest_telemetry() or get_drone_simulation_service().get_telemetry()
    return {
        "item": {
            **telemetry.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.get("/api/drone-simulation/events")
def get_drone_simulation_events_api(
    request: Request,
    limit: int = 50,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    repo = get_incident_repository()
    items = repo.list_events({"source_type": "drone_simulation", "limit": max(1, min(int(limit), 250))})
    payload = [
        {
            **item.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        }
        for item in items
    ]
    return {"items": payload, "count": len(payload), "status": "ok"}


@router.get("/api/drone-simulation/flight-path")
def get_drone_simulation_flight_path_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    items = get_drone_simulation_session_manager().get_flight_path()
    return {"items": [item.model_dump(mode="json") for item in items], "count": len(items), "status": "ok"}


def _command_response(
    request: Request,
    response,
    *,
    detail: str,
) -> dict:
    action = AuditAction.DRONE_COMMAND_ISSUED if response.success else AuditAction.DRONE_COMMAND_DENIED
    _audit(
        request,
        action,
        user=get_current_user_from_request(request),
        resource_id=_service_drone_id(),
        success=bool(response.success),
        detail=detail if response.success else (response.detail or detail),
        metadata={"command": response.command, "status": response.status},
    )
    return {"item": response.model_dump(mode="json"), "status": "ok" if response.success else "failed"}


@router.post("/api/drone-simulation/commands/takeoff")
def drone_takeoff_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    response = get_drone_simulation_session_manager().takeoff()
    return _command_response(request, response, detail="Simulated drone takeoff command issued")


@router.post("/api/drone-simulation/commands/land")
def drone_land_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    response = get_drone_simulation_session_manager().land()
    return _command_response(request, response, detail="Simulated drone land command issued")


@router.post("/api/drone-simulation/commands/hover")
def drone_hover_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    response = get_drone_simulation_session_manager().hover()
    return _command_response(request, response, detail="Simulated drone hover command issued")


@router.post("/api/drone-simulation/commands/move")
def drone_move_api(
    body: DroneCommandRequest,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    if body.x is None or body.y is None or body.z is None or body.velocity is None:
        raise HTTPException(status_code=400, detail="x, y, z, and velocity are required")
    response = get_drone_simulation_session_manager().move_to_position(body.x, body.y, body.z, body.velocity)
    return _command_response(request, response, detail="Simulated drone move command issued")


@router.get("/api/drone-simulation/frame/latest")
def get_drone_simulation_frame_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    manager = get_drone_simulation_session_manager()
    frame = manager.get_latest_frame() or get_drone_simulation_service().get_frame()
    _audit(
        request,
        AuditAction.DRONE_FRAME_ACCESSED,
        user=get_current_user_from_request(request),
        resource_id=_service_drone_id(),
        detail="Latest simulated drone frame accessed",
        metadata={"frame_index": frame.frame_index, "frame_available": frame.frame_available},
    )
    return {
        "item": {
            **frame.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.get("/api/drone-simulation/runtime-status")
def get_drone_runtime_status_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    status = get_drone_simulation_service().get_runtime_status()
    return {"item": status.model_dump(mode="json"), "status": "ok"}


@router.get("/api/drone-simulation/runtime")
def get_drone_runtime_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del request, current_user
    status = get_drone_simulation_service().get_runtime_status()
    return {
        "item": {
            **status.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.post("/api/drone-simulation/runtime/launch")
def launch_drone_runtime_api(
    body: dict | None,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    prefer = str((body or {}).get("prefer") or "AirSimNH")
    if prefer not in {"CityEnviron", "AirSimNH", "Blocks"}:
        raise HTTPException(status_code=400, detail="prefer must be CityEnviron, AirSimNH, or Blocks")
    command = [
        sys.executable,
        "scripts/launch_city_drone_runtime.py",
        "--prefer",
        prefer,
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    status = get_drone_simulation_service().get_runtime_status()
    return {
        "item": {
            "prefer": prefer,
            "returncode": completed.returncode,
            "output_tail": "\n".join(completed.stdout.splitlines()[-10:]),
            "runtime_status": status.model_dump(mode="json"),
        },
        "status": "ok" if completed.returncode == 0 else "failed",
    }


@router.post("/api/drone-simulation/stream/start")
def start_drone_stream_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    manager = get_drone_simulation_session_manager()
    session = manager.start_session(current_user)
    _audit(
        request,
        AuditAction.DRONE_SIMULATION_STARTED,
        user=get_current_user_from_request(request),
        resource_id=session.session_id,
        detail="Simulated drone stream started",
    )
    return {
        "item": {
            "session": session.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.post("/api/drone-simulation/stream/stop")
def stop_drone_stream_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    manager = get_drone_simulation_session_manager()
    session = manager.stop_session(current_user)
    _audit(
        request,
        AuditAction.DRONE_SIMULATION_STOPPED,
        user=get_current_user_from_request(request),
        resource_id=session.session_id,
        detail="Simulated drone stream stopped",
    )
    return {
        "item": {
            "session": session.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.post("/api/drone-simulation/missions/run-demo")
def run_drone_mission_demo_api(
    body: dict | None,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_control),
):
    del current_user
    mission = str((body or {}).get("mission") or "fixed_camera_handoff_demo")
    command = [
        sys.executable,
        "scripts/run_city_drone_mission_demo.py",
        "--mission",
        mission,
        "--device",
        "cuda",
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return {
        "item": {
            "mission": mission,
            "returncode": completed.returncode,
            "output_tail": "\n".join(completed.stdout.splitlines()[-12:]),
        },
        "status": "ok" if completed.returncode == 0 else "failed",
    }


@router.get("/api/drone-simulation/cameras")
def list_drone_simulation_cameras_api(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    service = get_drone_simulation_service()
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    items = [
        {
            "source_id": build_drone_source_id(service.drone_id, camera_name),
            "camera_name": camera_name,
            "source_type": "drone_simulation",
            "drone_id": service.drone_id,
            "simulated": True,
            "operator_review_required": True,
        }
        for camera_name in _service_camera_names(service)
    ]
    return {"items": items, "count": len(items), "status": "ok"}


@router.get("/api/drone-simulation/cameras/{camera_name}/latest-frame")
def get_drone_camera_latest_frame_api(
    camera_name: str,
    request: Request,
    response: Response,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del current_user
    normalized_name = str(camera_name).strip().lower()
    if normalized_name not in SUPPORTED_DRONE_CAMERAS:
        raise HTTPException(status_code=404, detail=f"Unsupported drone camera '{camera_name}'")
    ensure_stream_access(request, get_current_user_from_request(request), _service_drone_id())
    source_id = build_drone_source_id(_service_drone_id(), normalized_name)
    ensure_stream_access(request, get_current_user_from_request(request), source_id)
    manager = get_drone_simulation_session_manager()
    service = get_drone_simulation_service()
    frame = manager.get_latest_frame()
    if frame is None or frame.camera_name != normalized_name:
        frame = service.latest_frame(normalized_name) or service.get_camera_frame(normalized_name)
    for key, value in _sensitive_headers().items():
        response.headers[key] = value
    return {
        "item": {
            **frame.model_dump(mode="json"),
            "source_type": "drone_simulation",
            "simulated": True,
            "operator_review_required": True,
        },
        "status": "ok",
    }


@router.websocket("/ws/drone-simulation")
async def drone_simulation_ws(websocket: WebSocket):
    user = await authenticate_websocket(websocket, required_permission="drone:read")
    if user is None:
        return
    service = get_drone_simulation_service()
    if not has_permission(user.role, "stream:read", get_rbac_config()):
        await reject_ws(websocket, reason="stream:read permission is required")
        return
    if not can_access_camera(user, service.drone_id):
        await reject_ws(websocket, reason="Access denied for simulated drone stream")
        return
    await websocket.accept()
    manager = get_drone_simulation_session_manager()
    mission_repo = get_drone_mission_repository()
    fusion_repo = get_drone_fusion_repository()
    incident_repo = get_incident_repository()
    try:
        while True:
            telemetry = manager.get_latest_telemetry() or service.latest_telemetry() or service.get_telemetry()
            frame = manager.get_latest_frame() or service.latest_frame() or service.get_frame()
            runtime = service.get_runtime_status()
            mission_sessions = mission_repo.list_sessions(limit=1, offset=0)
            latest_mission = mission_sessions[-1].model_dump(mode="json") if mission_sessions else None
            latest_events = incident_repo.list_events({"source_type": "drone_simulation", "limit": 1})
            latest_event = latest_events[-1].model_dump(mode="json") if latest_events else None
            pending_fusion = fusion_repo.list_correlations(review_status="pending", limit=200)

            telemetry_payload = _ws_payload(
                "telemetry",
                {
                    "drone_id": service.drone_id,
                    "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else None,
                    "session": manager.get_session_status().model_dump(mode="json"),
                },
            )
            telemetry_payload["event_type"] = "drone_telemetry"
            await websocket.send_json(telemetry_payload)

            await websocket.send_json(
                {
                    **_ws_payload(
                        "frame_status",
                        {
                            "camera_name": frame.camera_name if frame is not None else "front_center",
                            "frame_available": bool(frame and frame.frame_available),
                            "frame_index": frame.frame_index if frame is not None else None,
                            "status": frame.status if frame is not None else "disconnected",
                            "last_error": frame.last_error if frame is not None else None,
                        },
                    ),
                    "event_type": "drone_frame_status",
                }
            )
            await websocket.send_json(
                {
                    **_ws_payload(
                        "runtime_status",
                        {
                            "selected_runtime": runtime.selected_runtime,
                            "available_runtimes": runtime.available_runtimes,
                            "fallback_used": runtime.fallback_used,
                            "connected": runtime.connected,
                            "port_open": runtime.port_open,
                        },
                    ),
                    "event_type": "drone_runtime_status",
                }
            )
            await websocket.send_json(
                {
                    **_ws_payload("mission_status", latest_mission or {"status": "idle"}),
                    "event_type": "drone_mission_status",
                }
            )
            await websocket.send_json(
                {
                    **_ws_payload("detection_event", latest_event or {"status": "no_event"}),
                    "event_type": "drone_detection_event",
                }
            )
            await websocket.send_json(
                {
                    **_ws_payload(
                        "fusion_update",
                        {
                            "pending_candidates": len(pending_fusion),
                            "latest_correlation_id": pending_fusion[-1].correlation_id if pending_fusion else None,
                        },
                    ),
                    "event_type": "drone_fusion_update",
                }
            )
            await asyncio.sleep(1.0)
    except BaseException:
        _audit(
            websocket,
            AuditAction.WEBSOCKET_DISCONNECTED,
            user=user,
            resource_id="/ws/drone-simulation",
            detail="Drone simulation websocket disconnected",
        )
