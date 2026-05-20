from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.security_models import UserAccount
from app.models.simulation_source_models import (
    SimCameraStatus,
    SimDroneStatus,
    SimulationObservationRequest,
)
from app.services.simulation_source_service import get_city_surveillance_registry


router = APIRouter(prefix="/api/simulation/sources", tags=["simulation"])


@router.get("/cameras")
def list_simulation_cameras(
    zone: str | None = Query(default=None, description="Filter by zone_id"),
    status: str | None = Query(default=None, description="Filter by status"),
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    cameras = registry.list_cameras(zone_id=zone)
    if status:
        normalized = str(status).lower()
        cameras = [c for c in cameras if c.status.value == normalized]
    return {
        "items": [c.to_dict() for c in cameras],
        "count": len(cameras),
        "status": "ok",
    }


@router.get("/cameras/{camera_id}")
def get_simulation_camera(
    camera_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    camera = registry.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Simulation camera '{camera_id}' not found")
    return {"item": camera.to_dict(), "status": "ok"}


@router.get("/drones")
def list_simulation_drones(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    drones = registry.list_drones()
    return {
        "items": [d.to_dict() for d in drones],
        "count": len(drones),
        "status": "ok",
    }


@router.get("/drones/{drone_id}")
def get_simulation_drone(
    drone_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    drone = registry.get_drone(drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail=f"Simulation drone '{drone_id}' not found")
    return {"item": drone.to_dict(), "status": "ok"}


@router.get("/dashboard-feeds")
def get_dashboard_feeds(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    feeds = registry.dashboard_feed_list()
    return {
        "items": [f.model_dump(mode="json") for f in feeds],
        "count": len(feeds),
        "status": "ok",
    }


@router.get("/snapshot")
def get_source_network_snapshot(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = get_city_surveillance_registry()
    return {"snapshot": registry.snapshot(), "status": "ok"}


@router.post("/observations")
def ingest_simulation_observation(
    observation: SimulationObservationRequest,
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    """
    Accept a structured simulation observation, validate source governance,
    and map it through the Phase 4 normalized intelligence event adapter.

    Returns the normalized intelligence event (dry-run — does not promote to
    alerts/incidents unless the observation is from a registered source).
    """
    del current_user
    registry = get_city_surveillance_registry()

    source_type = observation.source_type
    camera_id = observation.camera_id
    drone_id = observation.drone_id

    # Source governance validation
    zone: str | None = observation.zone
    source_meta: dict = {"simulated": True}

    if source_type == "simulation_cctv":
        if not camera_id:
            raise HTTPException(
                status_code=422,
                detail="simulation_cctv observations must include camera_id",
            )
        valid, result = registry.validate_camera_source(camera_id)
        if not valid:
            raise HTTPException(status_code=422, detail=result)
        zone = zone or result
        source_meta = registry.source_metadata(camera_id=camera_id)
        registry.mark_observation(camera_id)

    elif source_type == "drone_camera":
        if not drone_id:
            raise HTTPException(
                status_code=422,
                detail="drone_camera observations must include drone_id",
            )
        valid, result = registry.validate_drone_source(drone_id)
        if not valid:
            raise HTTPException(status_code=422, detail=result)
        zone = zone or result
        source_meta = registry.source_metadata(drone_id=drone_id)

    elif source_type == "scenario_observation":
        # Scenario observations may reference either a camera or a drone (or neither)
        if camera_id:
            valid, cam_zone = registry.validate_camera_source(camera_id)
            if not valid:
                raise HTTPException(status_code=422, detail=cam_zone)
            zone = zone or cam_zone
            source_meta = registry.source_metadata(camera_id=camera_id)
        if drone_id:
            valid, drone_zone = registry.validate_drone_source(drone_id)
            if not valid:
                raise HTTPException(status_code=422, detail=drone_zone)
            zone = zone or drone_zone
            source_meta.update(registry.source_metadata(drone_id=drone_id))

    # Build observation dict for the intelligence adapter
    obs_dict = observation.model_dump(mode="json")
    obs_dict["zone"] = zone
    obs_dict["metadata"] = {**source_meta, **obs_dict.get("metadata", {})}

    # Normalize via the simulation observation adapter
    try:
        from app.services.command_center_intelligence_service import CommandCenterIntelligenceService
        service = CommandCenterIntelligenceService()
        normalized = service.simulation_adapter.normalize_observation(obs_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Intelligence normalization failed: {str(exc)[:240]}",
        ) from exc

    return {
        "normalized_event": normalized.model_dump(mode="json"),
        "source_validated": True,
        "source_meta": source_meta,
        "status": "ok",
    }
