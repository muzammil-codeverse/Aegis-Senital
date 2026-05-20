from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.security_models import UserAccount
from app.services.scenario_engine_service import get_scenario_engine


router = APIRouter(prefix="/api/simulation/scenarios", tags=["simulation"])


class StartScenarioRequest(BaseModel):
    scenario_id: str
    mode: str = "step"


@router.get("")
def list_scenarios(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    engine = get_scenario_engine()
    return {
        "items": [s.model_dump(mode="json") for s in engine.list_scenarios()],
        "count": len(engine.list_scenarios()),
        "status": "ok",
    }


@router.get("/active")
def get_active_run(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    engine = get_scenario_engine()
    status = engine.active_run_status()
    if status is None:
        return {"active_run": None, "status": "idle"}
    return {"active_run": status.model_dump(mode="json"), "status": "ok"}


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    engine = get_scenario_engine()
    scenario = engine.get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    return {"item": scenario.model_dump(mode="json"), "status": "ok"}


@router.post("/start")
def start_scenario(
    body: StartScenarioRequest,
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    try:
        run = engine.start(body.scenario_id, mode=body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run": run.to_status().model_dump(mode="json"), "status": "ok"}


@router.post("/step")
def step_scenario(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    try:
        result = engine.step()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


@router.post("/pause")
def pause_scenario(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    try:
        status = engine.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run": status.model_dump(mode="json"), "status": "ok"}


@router.post("/resume")
def resume_scenario(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    try:
        status = engine.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run": status.model_dump(mode="json"), "status": "ok"}


@router.post("/cancel")
def cancel_scenario(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    try:
        status = engine.cancel()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run": status.model_dump(mode="json"), "status": "ok"}


@router.post("/reset")
def reset_scenario(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    engine = get_scenario_engine()
    engine.reset()
    return {"status": "ok", "message": "Scenario engine reset. No active run."}


@router.get("/run/status")
def get_run_status(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    engine = get_scenario_engine()
    status = engine.active_run_status()
    if status is None:
        return {"active_run": None, "status": "idle"}
    return {"active_run": status.model_dump(mode="json"), "status": "ok"}


@router.get("/run/timeline")
def get_run_timeline(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    engine = get_scenario_engine()
    run = engine.active_run()
    if run is None:
        return {"items": [], "count": 0, "status": "idle"}
    timeline = engine.run_observation_timeline()
    return {
        "run_id": run.run_id,
        "scenario_id": run.scenario_id,
        "items": timeline,
        "count": len(timeline),
        "status": "ok",
    }
