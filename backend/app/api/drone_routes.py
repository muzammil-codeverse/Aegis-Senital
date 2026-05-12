from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

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
from app.services.drone.drone_simulation_service import get_drone_simulation_service
from app.services.drone.drone_simulation_session_manager import get_drone_simulation_session_manager

router = APIRouter(tags=["drone-simulation"])


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
            "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else None,
            "latest_frame_available": bool(frame and frame.frame_available),
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
    return {"item": telemetry.model_dump(mode="json"), "status": "ok"}


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
    return {"item": frame.model_dump(mode="json"), "status": "ok"}


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
    try:
        while True:
            telemetry = manager.get_latest_telemetry() or service.latest_telemetry() or service.get_telemetry()
            payload = {
                "event_type": "drone_telemetry",
                "drone_id": service.drone_id,
                "simulated": True,
                "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else None,
                "session": manager.get_session_status().model_dump(mode="json"),
                "timestamp": _now_iso(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        _audit(
            websocket,
            AuditAction.WEBSOCKET_DISCONNECTED,
            user=user,
            resource_id="/ws/drone-simulation",
            detail="Drone simulation websocket disconnected",
        )
