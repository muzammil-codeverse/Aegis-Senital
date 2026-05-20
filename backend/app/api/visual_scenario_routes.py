"""
Phase XI + Phase XII — Visual Scenario API Routes.

REST endpoints that let the exhibition dashboard and external scripts trigger
the AirSim visual scene rendering, drive the visual clock in lock-step with
the scenario engine, and pull camera snapshots back into the UI.

Endpoints
---------
GET  /api/visual-scenario/status              — current controller status
GET  /api/visual-scenario/sync-status         — sync-service status (Phase XII)
POST /api/visual-scenario/setup               — draw static scene
POST /api/visual-scenario/animate             — start animation thread
POST /api/visual-scenario/stop                — stop animation
POST /api/visual-scenario/flush               — clear all debug markers
GET  /api/visual-scenario/config              — return loaded visual scenario config
GET  /api/visual-scenario/actors              — list actor IDs and current poses
GET  /api/visual-scenario/id-map              — Aegis actor/camera ID mapping
GET  /api/visual-scenario/real-actor-mode     — Phase XII fidelity probe
POST /api/visual-scenario/sync                — Phase XII: drive visual to t_offset
POST /api/visual-scenario/sync-step           — Phase XII: drive visual from step payload
GET  /api/visual-scenario/cameras             — Phase XII: visual camera + snapshot status
POST /api/visual-scenario/cameras/{id}/snapshot — Phase XII: capture one snapshot
POST /api/visual-scenario/cameras/snapshot-all  — Phase XII: capture all snapshots
GET  /api/visual-scenario/snapshots/{id}      — Phase XII: serve PNG snapshot file
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as FastApiPath
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/visual-scenario", tags=["visual-scenario"])

_VISUAL_JSON = (
    Path(__file__).resolve().parents[3]
    / "simulation"
    / "visual_scenarios"
    / "bank_robbery_visual.json"
)


# ---------------------------------------------------------------------------
# Lazy service accessors
# ---------------------------------------------------------------------------

def _get_controller():
    from app.services.visual_scenario_controller import get_visual_scenario_controller
    return get_visual_scenario_controller()


def _get_sync_service():
    from app.services.visual_scenario_sync_service import get_visual_scenario_sync_service
    return get_visual_scenario_sync_service()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AnimateRequest(BaseModel):
    duration_seconds: float = 65.0
    real_time_factor: float = 1.0


class SetupResponse(BaseModel):
    status: str
    zones: int = 0
    camera_markers: int = 0
    actors: int = 0
    drone_route: bool = False
    crime_markers: int = 0
    spawned_meshes: int = 0
    real_actor_mode: str = "unavailable"
    dry_run: bool = False
    error: str | None = None


class SyncRequest(BaseModel):
    t_offset_seconds: float
    camera_id: str | None = None
    capture_snapshot: bool | None = None


class SyncStepRequest(BaseModel):
    """Mirror of ScenarioEngineService.step() return payload."""
    step: int | None = None
    t_offset_seconds: float | None = None
    event_type: str | None = None
    observation: dict | None = None


class StartDemoRequest(BaseModel):
    scenario_run_id: str | None = None
    duration_seconds: float = 65.0


class StopDemoRequest(BaseModel):
    flush_markers: bool = False


# ---------------------------------------------------------------------------
# Phase XI routes (preserved)
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_visual_scenario_status() -> dict:
    try:
        ctrl = _get_controller()
        return {"status": "ok", "controller": ctrl.get_status()}
    except Exception as exc:
        logger.error("visual-scenario status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/setup", response_model=SetupResponse)
async def setup_visual_scene() -> SetupResponse:
    """Draw the static scene (zones, camera markers, actors, drone route)."""
    try:
        ctrl = _get_controller()
        result = await run_in_threadpool(ctrl.setup_static_scene)
        return SetupResponse(
            status="ok" if not result.get("error") else "partial",
            zones=int(result.get("zones", 0)),
            camera_markers=int(result.get("camera_markers", 0)),
            actors=int(result.get("actors", 0)),
            drone_route=bool(result.get("drone_route", False)),
            crime_markers=int(result.get("crime_markers", 0)),
            spawned_meshes=int(result.get("spawned_meshes", 0)),
            real_actor_mode=str(result.get("real_actor_mode", "unavailable")),
            dry_run=bool(result.get("dry_run", False)),
            error=result.get("error"),
        )
    except Exception as exc:
        logger.error("visual-scenario setup error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/animate")
async def start_visual_animation(body: AnimateRequest) -> dict:
    try:
        ctrl = _get_controller()
        ctrl._rtf = max(0.1, float(body.real_time_factor))  # noqa: SLF001
        await run_in_threadpool(ctrl.start_animation_thread, duration=float(body.duration_seconds))
        return {
            "status": "ok",
            "message": f"Animation started (duration={body.duration_seconds}s, rtf={body.real_time_factor})",
            "controller": ctrl.get_status(),
        }
    except Exception as exc:
        logger.error("visual-scenario animate error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
async def stop_visual_animation() -> dict:
    try:
        ctrl = _get_controller()
        await run_in_threadpool(ctrl.stop_animation)
        return {"status": "ok", "message": "Animation stopped", "controller": ctrl.get_status()}
    except Exception as exc:
        logger.error("visual-scenario stop error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/flush")
async def flush_visual_markers() -> dict:
    try:
        ctrl = _get_controller()
        await run_in_threadpool(ctrl.flush_markers)
        return {"status": "ok", "message": "All persistent markers cleared"}
    except Exception as exc:
        logger.error("visual-scenario flush error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config")
async def get_visual_scenario_config() -> dict:
    if not _VISUAL_JSON.exists():
        raise HTTPException(status_code=404, detail="Visual scenario config not found")
    try:
        data = json.loads(_VISUAL_JSON.read_text(encoding="utf-8"))
        return {"status": "ok", "config": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/actors")
async def list_visual_actors() -> dict:
    try:
        ctrl = _get_controller()
        actors_out = []
        for actor_id, actor in ctrl._actors.items():  # noqa: SLF001
            actors_out.append({
                "actor_id": actor_id,
                "label": actor.label,
                "color_rgba": actor.color,
                "active": actor.active,
                "role": actor.role,
                "current_pose": {
                    "x": actor.current_pose.x,
                    "y": actor.current_pose.y,
                    "z": actor.current_pose.z,
                },
                "waypoint_count": len(actor.waypoints),
                "is_group": len(actor.group_members) > 0,
                "group_size": len(actor.group_members),
                "spawned_object_name": actor.spawned_object_name,
            })
        return {"status": "ok", "actors": actors_out, "count": len(actors_out)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/id-map")
async def get_aegis_id_map() -> dict:
    if not _VISUAL_JSON.exists():
        raise HTTPException(status_code=404, detail="Visual scenario config not found")
    try:
        data = json.loads(_VISUAL_JSON.read_text(encoding="utf-8"))
        return {
            "status": "ok",
            "aegis_id_map": data.get("aegis_id_map", {}),
            "scenario_id": data.get("scenario_id"),
            "linked_scenario_id": data.get("linked_scenario_id"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Phase XII routes
# ---------------------------------------------------------------------------

@router.get("/real-actor-mode")
async def get_real_actor_mode() -> dict:
    """Probe the simulator and return the current visual fidelity mode."""
    try:
        ctrl = _get_controller()

        def _probe() -> tuple[str, list[str]]:
            if not ctrl._client:  # noqa: SLF001
                ctrl.connect()
            mode = ctrl.probe_real_actor_mode()
            assets = ctrl.list_available_assets()
            return mode, assets

        mode, assets = await run_in_threadpool(_probe)
        return {
            "status": "ok",
            "real_actor_mode": mode,
            "available_asset_count": len(assets),
            "available_assets_preview": assets[:20],
        }
    except Exception as exc:
        logger.error("real-actor-mode error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sync-status")
async def get_sync_status() -> dict:
    try:
        sync = _get_sync_service()
        return {"status": "ok", "sync": sync.get_status()}
    except Exception as exc:
        logger.error("sync-status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync")
async def sync_visual_to_offset(body: SyncRequest) -> dict:
    """Push the visual clock to a specific t_offset_seconds."""
    try:
        sync = _get_sync_service()
        result = await run_in_threadpool(
            sync.sync_to_offset,
            body.t_offset_seconds,
            camera_id=body.camera_id,
            capture_snapshot=body.capture_snapshot,
        )
        return {
            "status": "ok",
            "result": result,
        }
    except Exception as exc:
        logger.error("sync error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync-step")
async def sync_visual_from_step(body: SyncStepRequest) -> dict:
    """Drive the visual world from a ScenarioEngineService.step() payload."""
    try:
        sync = _get_sync_service()
        result = await run_in_threadpool(sync.handle_step, body.model_dump())
        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.error("sync-step error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/demo/start")
async def visual_demo_start(body: StartDemoRequest) -> dict:
    """Start the visual demo: build the static scene + start animation."""
    try:
        sync = _get_sync_service()
        return await run_in_threadpool(
            sync.start_for_demo,
            scenario_run_id=body.scenario_run_id,
            duration=body.duration_seconds,
        )
    except Exception as exc:
        logger.error("visual demo/start error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/demo/stop")
async def visual_demo_stop(body: StopDemoRequest) -> dict:
    """Stop the visual demo animation, optionally flushing markers."""
    try:
        sync = _get_sync_service()
        return await run_in_threadpool(sync.stop_for_demo, flush_markers=body.flush_markers)
    except Exception as exc:
        logger.error("visual demo/stop error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cameras")
async def list_visual_cameras() -> dict:
    """Return per-camera visual sync + snapshot status."""
    try:
        sync = _get_sync_service()
        cameras = await run_in_threadpool(sync.list_camera_status)
        return {"status": "ok", "cameras": cameras}
    except Exception as exc:
        logger.error("cameras error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cameras/{camera_id}/snapshot")
async def capture_single_camera(camera_id: str = FastApiPath(...)) -> dict:
    try:
        sync = _get_sync_service()
        return await run_in_threadpool(sync.capture_camera, camera_id)
    except Exception as exc:
        logger.error("capture %s error: %s", camera_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cameras/snapshot-all")
async def capture_all_cameras() -> dict:
    try:
        sync = _get_sync_service()
        return await run_in_threadpool(sync.capture_all_snapshots)
    except Exception as exc:
        logger.error("capture all error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/snapshots/{camera_id}")
async def get_snapshot(camera_id: str = FastApiPath(...)):
    """Serve the saved PNG snapshot for a camera id."""
    try:
        sync = _get_sync_service()
        snapshot_path = sync.snapshot_path_for(camera_id)
        if not snapshot_path.exists():
            raise HTTPException(status_code=404, detail=f"No snapshot for {camera_id}")
        return FileResponse(
            path=str(snapshot_path),
            media_type="image/png",
            filename=f"{camera_id}.png",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("snapshot serve %s error: %s", camera_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
