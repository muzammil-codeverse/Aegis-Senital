from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.security_dependencies import require_permission as require_api_permission
from app.core.preflight import PreflightMode, PreflightRunRequest, get_preflight_service
from app.models.security_models import UserAccount


router = APIRouter(prefix="/api/preflight", tags=["preflight"])


def _triggered_by(user: UserAccount | None) -> str | None:
    if user is None:
        return None
    return user.username or user.user_id


@router.get("/modes")
def list_preflight_modes_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    return {
        "items": [
            {
                "mode": PreflightMode.QUICK.value,
                "description": "Fast readiness check for API shell, auth, storage, and capability registry.",
                "supports_warmup": False,
            },
            {
                "mode": PreflightMode.EXHIBITION.value,
                "description": "Safe exhibition readiness check for all core capability groups with controlled warmup.",
                "supports_warmup": True,
            },
            {
                "mode": PreflightMode.DEEP.value,
                "description": "Registered for later admin use; heavy Phase 5 warmup sequencing is not executed in Phase 2.",
                "supports_warmup": False,
            },
        ],
        "count": 3,
        "status": "ok",
    }


@router.get("/latest")
def get_latest_preflight_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    run = get_preflight_service().get_latest_preflight()
    return {"item": run.model_dump(mode="json"), "status": "ok"}


@router.get("/summary")
def get_preflight_summary_api(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    summary = get_preflight_service().summarize_preflight_results()
    return {"item": summary.model_dump(mode="json"), "status": "ok"}


@router.post("/run")
def run_preflight_api(
    body: PreflightRunRequest,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    try:
        run = get_preflight_service().start_preflight(
            body.mode,
            selected_capabilities=body.selected_capabilities,
            triggered_by=_triggered_by(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"item": run.model_dump(mode="json"), "status": "ok"}


@router.get("/runs/{run_id}")
def get_preflight_run_api(
    run_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    try:
        run = get_preflight_service().get_preflight_run(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Preflight run '{run_id}' not found")
    return {"item": run.model_dump(mode="json"), "status": "ok"}


@router.post("/capabilities/{capability_id}/check")
def check_preflight_capability_api(
    capability_id: str,
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    try:
        result = get_preflight_service().evaluate_capability(capability_id, PreflightMode.EXHIBITION)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Capability '{capability_id}' not found")
    return {"item": result.model_dump(mode="json"), "status": "ok"}

