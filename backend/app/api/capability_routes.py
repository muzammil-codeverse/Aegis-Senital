from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.security_dependencies import require_permission as require_api_permission
from app.core.capabilities import (
    aggregate_capability_health,
    get_capability_registry,
    refresh_all_capability_statuses,
    refresh_capability_status,
    register_default_capabilities,
)
from app.models.security_models import UserAccount


router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


def _registry():
    registry = register_default_capabilities(get_capability_registry())
    return registry


@router.get("")
def list_capabilities_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = _registry()
    items = registry.to_api_list()
    return {
        "items": items,
        "count": len(items),
        "status": "ok" if items else "empty",
        "dependencies": registry.dependency_overview(),
    }


@router.get("/summary")
def capability_summary_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = _registry()
    summary = aggregate_capability_health(registry.list())
    return {"item": summary, "status": "ok"}


@router.post("/refresh")
def refresh_capabilities_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = _registry()
    refresh_all_capability_statuses(registry)
    items = registry.to_api_list()
    return {
        "items": items,
        "count": len(items),
        "summary": aggregate_capability_health(registry.list()),
        "status": "ok" if items else "empty",
    }


@router.get("/{capability_id}")
def get_capability_api(
    capability_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = _registry()
    try:
        record = registry.get(capability_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")
    return {"item": record.to_api_dict(), "status": "ok"}


@router.post("/{capability_id}/check")
def check_capability_api(
    capability_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    registry = _registry()
    try:
        record = refresh_capability_status(registry, capability_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")
    return {"item": record.to_api_dict(), "status": "ok"}
