"""Phase 9 — Exhibition Demo API routes.

All endpoints require at minimum system:read (GET) or operator:write (POST).
No anonymous access.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.security_models import UserAccount
from app.services.exhibition_demo_service import get_exhibition_demo_service


router = APIRouter(prefix="/api/exhibition-demo", tags=["exhibition-demo"])


class StartDemoRequest(BaseModel):
    mode: str = "step"
    run_preflight: bool = False


# ---------------------------------------------------------------------------
# GET /api/exhibition-demo/status
# ---------------------------------------------------------------------------

@router.get("/status")
def get_demo_status(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    svc = get_exhibition_demo_service()
    return {"item": svc.get_demo_status(), "status": "ok"}


# ---------------------------------------------------------------------------
# POST /api/exhibition-demo/reset
# ---------------------------------------------------------------------------

@router.post("/reset")
def reset_demo(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    svc = get_exhibition_demo_service()
    result = svc.reset_demo()
    return result


# ---------------------------------------------------------------------------
# POST /api/exhibition-demo/start
# ---------------------------------------------------------------------------

@router.post("/start")
def start_demo(
    body: StartDemoRequest,
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    if body.mode not in ("step", "auto"):
        raise HTTPException(status_code=400, detail="mode must be 'step' or 'auto'")
    svc = get_exhibition_demo_service()
    try:
        result = svc.start_demo(mode=body.mode, run_preflight=body.run_preflight)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


# ---------------------------------------------------------------------------
# POST /api/exhibition-demo/step
# ---------------------------------------------------------------------------

@router.post("/step")
def step_demo(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    svc = get_exhibition_demo_service()
    try:
        result = svc.step_demo()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


# ---------------------------------------------------------------------------
# POST /api/exhibition-demo/auto-run
# ---------------------------------------------------------------------------

@router.post("/auto-run")
def auto_run_demo(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    svc = get_exhibition_demo_service()
    try:
        result = svc.auto_run_demo()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


# ---------------------------------------------------------------------------
# POST /api/exhibition-demo/cancel
# ---------------------------------------------------------------------------

@router.post("/cancel")
def cancel_demo(
    current_user: UserAccount = Depends(require_api_permission("operator:write")),
):
    del current_user
    svc = get_exhibition_demo_service()
    result = svc.cancel_demo()
    return result


# ---------------------------------------------------------------------------
# GET /api/exhibition-demo/snapshot
# ---------------------------------------------------------------------------

@router.get("/snapshot")
def get_demo_snapshot(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    svc = get_exhibition_demo_service()
    snapshot = svc.get_demo_snapshot()
    return {"item": snapshot, "status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/exhibition-demo/runbook
# ---------------------------------------------------------------------------

@router.get("/runbook")
def get_runbook(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    svc = get_exhibition_demo_service()
    runbook = svc.get_runbook()
    return {"item": runbook, "status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/exhibition-demo/fallback
# Part E — deterministic replay mode when scenario engine is unavailable
# ---------------------------------------------------------------------------

@router.get("/fallback")
def get_fallback_snapshot(
    current_user: UserAccount = Depends(require_api_permission("system:read")),
):
    del current_user
    svc = get_exhibition_demo_service()
    try:
        fallback = svc.get_fallback_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Fallback unavailable: {exc}")
    return {"item": fallback, "status": "ok"}
