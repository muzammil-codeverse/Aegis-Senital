"""Phase 8 — Unified drone operational state API.

All endpoints are read-only snapshots merged from registry + scenario + AirSim.
AirSim connection is optional; endpoints return valid data regardless.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.security_dependencies import require_permission as require_api_permission
from app.services.drone_operational_state_service import get_drone_operational_state_service

router = APIRouter(prefix="/api/drone-unified", tags=["drone-unified"])


@router.get("/fleet")
def get_unified_fleet(
    _user=Depends(require_api_permission("system:read")),
):
    """Return unified operational state for all drones in the city registry."""
    svc = get_drone_operational_state_service()
    fleet = svc.get_unified_fleet()
    return {
        "status": "ok",
        "item": fleet.model_dump(mode="json"),
    }


@router.get("/drones/{drone_id}")
def get_unified_drone(
    drone_id: str,
    _user=Depends(require_api_permission("system:read")),
):
    """Return unified operational state for a single drone."""
    svc = get_drone_operational_state_service()
    state = svc.get_unified_drone(drone_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Drone '{drone_id}' not found in registry.")
    return {
        "status": "ok",
        "item": state.model_dump(mode="json"),
    }


@router.get("/health")
def drone_unified_health():
    """Health check for the unified drone state service."""
    svc = get_drone_operational_state_service()
    return svc.health()
