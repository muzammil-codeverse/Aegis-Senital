from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.security_models import UserAccount
from app.services.fused_path_service import get_fused_path_service
from app.services.scenario_engine_service import get_scenario_engine

router = APIRouter(prefix="/api/simulation/scenarios/runs", tags=["tracking"])


def _require_run(run_id: str):
    engine = get_scenario_engine()
    run = engine.active_run()
    if run is None or run.run_id != run_id:
        raise HTTPException(status_code=404, detail=f"Scenario run '{run_id}' not found or not active.")
    return run


@router.get("/{run_id}/tracking")
def get_fused_tracking(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    _require_run(run_id)
    svc = get_fused_path_service()
    track = svc.get_fused_track(run_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"Fused track not yet available for run '{run_id}'.")
    return {"item": track.model_dump(mode="json"), "status": "ok"}


@router.get("/{run_id}/suspect-path")
def get_suspect_path(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    _require_run(run_id)
    svc = get_fused_path_service()
    waypoints = svc.get_suspect_path(run_id)
    return {
        "run_id": run_id,
        "actor_id": "SUSPECT-001",
        "items": [w.model_dump(mode="json") for w in waypoints],
        "count": len(waypoints),
        "status": "ok",
    }


@router.get("/{run_id}/camera-handoffs")
def get_camera_handoffs(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    _require_run(run_id)
    svc = get_fused_path_service()
    handoffs = svc.get_camera_handoffs(run_id)
    return {
        "run_id": run_id,
        "items": [h.model_dump(mode="json") for h in handoffs],
        "count": len(handoffs),
        "status": "ok",
    }


@router.get("/{run_id}/drone-route")
def get_drone_route(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    _require_run(run_id)
    svc = get_fused_path_service()
    route = svc.get_drone_route(run_id)
    if route is None:
        return {"run_id": run_id, "drone_route": None, "status": "not_dispatched"}
    return {"run_id": run_id, "drone_route": route.model_dump(mode="json"), "status": "ok"}


@router.get("/{run_id}/operational-view")
def get_operational_view(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    _require_run(run_id)
    svc = get_fused_path_service()
    view = svc.get_operational_view(run_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Operational view not available for run '{run_id}'.")
    return {"item": view, "status": "ok"}
