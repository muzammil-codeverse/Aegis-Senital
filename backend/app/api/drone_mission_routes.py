"""REST + WebSocket endpoints for the Drone Patrol Mission Planner (Phase 45).

All missions are simulated-only.
RBAC permissions: drone:read, drone:control, drone:mission, gis:read, stream:read.
Every lifecycle event is audited.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.api.security_dependencies import (
    get_current_user_from_request,
    require_permission as require_api_permission,
)
from app.api.websocket_security import authenticate_websocket, reject_ws
from app.models.drone_mission_models import (
    DroneMissionCreateRequest,
    DroneMissionPlan,
    DroneMissionSession,
    DroneMissionStartRequest,
    DroneMissionStatus,
)
from app.models.security_models import AuditAction, UserAccount
from app.security.config import get_rbac_config
from app.security.permissions import has_permission
from app.services.audit_log_service import get_audit_log_service
from app.services.drone.drone_mission_execution_service import (
    MissionExecutionError,
    get_drone_mission_execution_service,
)
from app.services.drone.drone_mission_evidence_service import get_drone_mission_evidence_service
from app.services.drone.drone_mission_service import (
    ValidationError,
    get_drone_mission_service,
)
from app.repositories.drone_mission_repository import get_drone_mission_repository

router = APIRouter(tags=["drone-mission"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
            resource_type="drone_mission",
            resource_id=resource_id,
            success=success,
            detail=detail,
            request=request,
            metadata=metadata,
        )
    except Exception:
        pass


def _require_permission(user: UserAccount, permission: str) -> None:
    if not has_permission(user.role, permission, get_rbac_config()):
        raise HTTPException(status_code=403, detail=f"{permission} permission is required")


def _require_drone_read(
    current_user: UserAccount = Depends(require_api_permission("drone:read")),
) -> UserAccount:
    _require_permission(current_user, "gis:read")
    return current_user


def _require_drone_mission(
    current_user: UserAccount = Depends(require_api_permission("drone:mission")),
) -> UserAccount:
    _require_permission(current_user, "drone:control")
    return current_user


def _load_city_mission_presets() -> list[dict[str, Any]]:
    path = PROJECT_ROOT / "configs" / "runtime" / "drone_city_missions.yaml"
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list((payload.get("drone_city_missions") or {}).get("presets") or [])


def _route_points_for_runtime(preset: dict[str, Any], runtime_name: str) -> list[dict[str, Any]]:
    routes = dict(preset.get("routes") or {})
    runtime = str(runtime_name or "").strip()
    if runtime == "CityEnviron":
        points = list(routes.get("city_route") or [])
    elif runtime == "Blocks":
        points = list(routes.get("compact_route") or [])
    else:
        points = list(routes.get("neighborhood_route") or [])
    if points:
        return points
    return list(preset.get("waypoints") or [])


@router.get("/api/drone-missions/presets/city")
def list_city_mission_presets(
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del request, current_user
    items = _load_city_mission_presets()
    return {"items": items, "count": len(items), "status": "ok"}


@router.post("/api/drone-missions/presets/{preset_name}/import")
def import_city_mission_preset(
    preset_name: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    svc = get_drone_mission_service()
    preset = None
    for item in _load_city_mission_presets():
        if str(item.get("name")) == preset_name:
            preset = item
            break
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")
    runtime_name = str((request.query_params.get("runtime") or "AirSimNH")).strip()
    if runtime_name not in {"CityEnviron", "AirSimNH", "Blocks"}:
        raise HTTPException(status_code=400, detail="runtime must be CityEnviron, AirSimNH, or Blocks")
    points = _route_points_for_runtime(preset, runtime_name)
    request_model = DroneMissionCreateRequest.model_validate(
        {
            "name": f"City preset: {preset_name}",
            "description": preset.get("description"),
            "route_type": "linear",
            "waypoints": [
                {
                    "sequence_index": idx,
                    "latitude": point.get("lat"),
                    "longitude": point.get("lon"),
                    "altitude_meters": point.get("altitude_m", 40),
                    "velocity_mps": float(point.get("velocity_mps") or 5.0),
                    "hold_seconds": float(point.get("hold_seconds") or preset.get("dwell_seconds") or 2),
                    "camera_action": "hover_and_observe",
                    "metadata": {
                        "action": point.get("action"),
                        "simulated_geo": True,
                        "demo": True,
                        "simulated": True,
                        "operator_review_required": True,
                    },
                }
                for idx, point in enumerate(points)
            ],
            "metadata": {
                "city_preset": preset_name,
                "runtime": runtime_name,
                "camera": preset.get("camera"),
                "expected_demo_outcome": preset.get("expected_demo_outcome"),
                "safe_wording": preset.get("safe_wording"),
                "runtime_compatibility": preset.get("runtime_compatibility"),
                "simulated_geo": True,
                "demo": True,
                "simulated": True,
                "operator_review_required": True,
            },
        }
    )
    mission = svc.create_mission(request_model, created_by=current_user.username)
    _audit(
        request,
        AuditAction.DRONE_MISSION_CREATED,
        user=current_user,
        resource_id=mission.mission_id,
        detail=f"City mission preset imported: {preset_name}",
        metadata={"preset": preset_name},
    )
    return {"item": mission.model_dump(mode="json"), "status": "ok"}


# ---------------------------------------------------------------------------
# Mission CRUD
# ---------------------------------------------------------------------------

@router.get("/api/drone-missions")
def list_drone_missions(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserAccount = Depends(_require_drone_read),
):
    """List simulated drone patrol missions."""
    svc = get_drone_mission_service()
    status_filter: DroneMissionStatus | None = None
    if status:
        try:
            status_filter = DroneMissionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    missions = svc.list_missions(status=status_filter, limit=limit, offset=offset)
    _audit(request, AuditAction.DRONE_MISSION_VIEWED, user=current_user, resource_id="list")
    return {
        "items": [m.model_dump(mode="json") for m in missions],
        "count": len(missions),
        "status": "ok",
    }


@router.post("/api/drone-missions")
def create_drone_mission(
    body: DroneMissionCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Create a new simulated drone patrol mission plan."""
    svc = get_drone_mission_service()
    try:
        mission = svc.create_mission(body, created_by=current_user.username)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _audit(
        request,
        AuditAction.DRONE_MISSION_CREATED,
        user=current_user,
        resource_id=mission.mission_id,
        detail=f"Simulated patrol mission created: {mission.name}",
        metadata={"waypoint_count": len(mission.waypoints)},
    )
    return {"item": mission.model_dump(mode="json"), "status": "ok"}


@router.get("/api/drone-missions/{mission_id}")
def get_drone_mission(
    mission_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    """Get a simulated drone patrol mission plan."""
    svc = get_drone_mission_service()
    mission = svc.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    _audit(request, AuditAction.DRONE_MISSION_VIEWED, user=current_user, resource_id=mission_id)
    return {"item": mission.model_dump(mode="json"), "status": "ok"}


@router.patch("/api/drone-missions/{mission_id}")
def update_drone_mission(
    mission_id: str,
    body: dict,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Update a simulated drone patrol mission plan."""
    svc = get_drone_mission_service()
    # Only DRAFT missions may be updated
    existing = svc.get_mission(mission_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if existing.status not in (DroneMissionStatus.DRAFT, DroneMissionStatus.PENDING_REVIEW):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update mission in status '{existing.status.value}'",
        )
    # Prevent overwriting safety flags
    body.pop("simulated", None)
    body.pop("operator_review_required", None)
    updated = svc.update_mission(mission_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="Mission not found after update")
    _audit(
        request,
        AuditAction.DRONE_MISSION_UPDATED,
        user=current_user,
        resource_id=mission_id,
        detail="Simulated patrol mission updated",
    )
    return {"item": updated.model_dump(mode="json"), "status": "ok"}


@router.delete("/api/drone-missions/{mission_id}")
def delete_drone_mission(
    mission_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Delete a DRAFT simulated drone patrol mission."""
    svc = get_drone_mission_service()
    try:
        found = svc.delete_mission(mission_id)
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not found:
        raise HTTPException(status_code=404, detail="Mission not found")
    _audit(
        request,
        AuditAction.DRONE_MISSION_DELETED,
        user=current_user,
        resource_id=mission_id,
        detail="Simulated patrol mission deleted",
    )
    return {"status": "ok", "detail": "Mission deleted"}


# ---------------------------------------------------------------------------
# Mission execution
# ---------------------------------------------------------------------------

@router.post("/api/drone-missions/{mission_id}/start")
def start_drone_mission(
    mission_id: str,
    body: DroneMissionStartRequest,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Start executing a simulated drone patrol mission."""
    plan_svc = get_drone_mission_service()
    exec_svc = get_drone_mission_execution_service()
    repo = get_drone_mission_repository()

    mission = plan_svc.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.status not in (
        DroneMissionStatus.DRAFT,
        DroneMissionStatus.APPROVED,
        DroneMissionStatus.PENDING_REVIEW,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Mission cannot be started from status '{mission.status.value}'",
        )

    # Create a new execution session
    session = DroneMissionSession(
        mission_id=mission_id,
        drone_id=mission.assigned_drone_id,
        total_waypoints=len(mission.waypoints),
        started_by=current_user.username,
    )
    repo.start_session(session)

    # Delegate to execution service
    session = exec_svc.start_mission(mission, session, started_by=current_user.username)

    _audit(
        request,
        AuditAction.DRONE_MISSION_STARTED,
        user=current_user,
        resource_id=mission_id,
        detail=f"Simulated aerial patrol mission started; session={session.session_id}",
        metadata={"session_id": session.session_id, "status": session.status.value},
    )
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.post("/api/drone-missions/sessions/{session_id}/pause")
def pause_drone_mission_session(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Pause a running simulated patrol mission session."""
    exec_svc = get_drone_mission_execution_service()
    try:
        session = exec_svc.pause_mission(session_id)
    except MissionExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _audit(request, AuditAction.DRONE_MISSION_PAUSED, user=current_user, resource_id=session_id)
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.post("/api/drone-missions/sessions/{session_id}/resume")
def resume_drone_mission_session(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Resume a paused simulated patrol mission session."""
    exec_svc = get_drone_mission_execution_service()
    try:
        session = exec_svc.resume_mission(session_id)
    except MissionExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _audit(request, AuditAction.DRONE_MISSION_RESUMED, user=current_user, resource_id=session_id)
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.post("/api/drone-missions/sessions/{session_id}/cancel")
def cancel_drone_mission_session(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_mission),
):
    """Cancel an active simulated patrol mission session."""
    exec_svc = get_drone_mission_execution_service()
    try:
        session = exec_svc.cancel_mission(session_id, reason="Operator cancellation")
    except MissionExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _audit(request, AuditAction.DRONE_MISSION_CANCELLED, user=current_user, resource_id=session_id)
    return {"item": session.model_dump(mode="json"), "status": "ok"}


# ---------------------------------------------------------------------------
# Session data endpoints
# ---------------------------------------------------------------------------

@router.get("/api/drone-missions/sessions/{session_id}/status")
def get_drone_mission_session_status(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    """Get current status and progress of a simulated mission session."""
    exec_svc = get_drone_mission_execution_service()
    status = exec_svc.get_mission_status(session_id)
    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Session not found")
    _audit(request, AuditAction.DRONE_MISSION_VIEWED, user=current_user, resource_id=session_id)
    return {"item": status, "status": "ok"}


@router.get("/api/drone-missions/sessions/{session_id}/telemetry")
def get_drone_mission_telemetry(
    session_id: str,
    request: Request,
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    current_user: UserAccount = Depends(_require_drone_read),
):
    """Get telemetry points for a simulated mission session."""
    repo = get_drone_mission_repository()
    points = repo.list_telemetry(session_id, limit=limit, offset=offset)
    _audit(
        request,
        AuditAction.DRONE_MISSION_TELEMETRY_VIEWED,
        user=current_user,
        resource_id=session_id,
    )
    return {
        "items": [p.model_dump(mode="json") for p in points],
        "count": len(points),
        "status": "ok",
    }


@router.get("/api/drone-missions/sessions/{session_id}/events")
def get_drone_mission_events(
    session_id: str,
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: UserAccount = Depends(_require_drone_read),
):
    """Get lifecycle events for a simulated mission session."""
    repo = get_drone_mission_repository()
    events = repo.list_events(session_id=session_id, limit=limit, offset=offset)
    _audit(request, AuditAction.DRONE_MISSION_VIEWED, user=current_user, resource_id=session_id)
    return {
        "items": [e.model_dump(mode="json") for e in events],
        "count": len(events),
        "status": "ok",
    }


@router.get("/api/drone-missions/sessions/{session_id}/report")
def get_drone_mission_report(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    """Get the post-mission report for a simulated patrol session."""
    repo = get_drone_mission_repository()
    report = repo.get_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not available for this session")
    _audit(
        request,
        AuditAction.DRONE_MISSION_REPORT_VIEWED,
        user=current_user,
        resource_id=session_id,
    )
    return {"item": report.model_dump(mode="json"), "status": "ok"}


@router.get("/api/drone-missions/sessions/{session_id}/evidence-bundle")
def get_drone_mission_evidence_bundle(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(_require_drone_read),
):
    del request, current_user
    bundle = get_drone_mission_evidence_service().build_mission_evidence_bundle(session_id)
    return {"item": bundle, "status": "ok"}


# ---------------------------------------------------------------------------
# Task 9: WebSocket — mission telemetry streaming
# ---------------------------------------------------------------------------

@router.websocket("/ws/drone-missions/{session_id}")
async def drone_mission_telemetry_ws(session_id: str, websocket: WebSocket):
    """Stream live telemetry for a simulated drone patrol mission session."""
    user = await authenticate_websocket(websocket, required_permission="drone:read")
    if user is None:
        return
    if not has_permission(user.role, "gis:read", get_rbac_config()):
        await reject_ws(websocket, reason="gis:read permission is required")
        return

    await websocket.accept()
    repo = get_drone_mission_repository()
    exec_svc = get_drone_mission_execution_service()

    try:
        while True:
            status = exec_svc.get_mission_status(session_id)
            points = repo.list_telemetry(session_id, limit=1, offset=max(0, status.get("telemetry_count", 0) - 1))
            latest_telemetry = points[-1].model_dump(mode="json") if points else None
            payload = {
                "event_type": "drone_mission_telemetry",
                "session_id": session_id,
                "simulated": True,
                "status": status,
                "latest_telemetry": latest_telemetry,
                "timestamp": _now_iso(),
            }
            await websocket.send_json(payload)
            # Stop streaming when terminal state reached
            if status.get("status") in ("completed", "cancelled", "failed", "not_found"):
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
