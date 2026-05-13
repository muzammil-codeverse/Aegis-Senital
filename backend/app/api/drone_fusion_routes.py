"""Phase 46 — Drone + Fixed Camera Fusion REST endpoints + WebSocket.

Permissions:
  drone_fusion:read   — list observations, correlations, handoffs, timeline
  drone_fusion:write  — run correlation, suggest handoffs
  drone_fusion:review — accept/reject/inconclusive correlation

Audit events:
  drone_fusion_correlation_created
  drone_fusion_correlation_reviewed
  drone_fusion_correlation_rejected
  drone_fusion_handoff_suggested
  drone_fusion_access_denied
"""
from __future__ import annotations

import asyncio
import json
import logging
import weakref
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.api.security_dependencies import (
    get_current_user_from_request,
    require_permission as require_api_permission,
)
from app.api.websocket_security import authenticate_websocket, reject_ws
from app.models.drone_fusion_models import (
    CrossSourceCorrelation,
    DroneCameraHandoff,
    FusionCorrelateRequest,
    FusionCorrelationListResponse,
    FusionHandoffListResponse,
    FusionObservation,
    FusionObservationListResponse,
    FusionReviewRequest,
    HandoffSuggestForEventRequest,
    HandoffSuggestForMissionRequest,
)
from app.models.security_models import AuditAction, UserAccount
from app.security.config import get_rbac_config
from app.security.permissions import has_permission
from app.services.audit_log_service import get_audit_log_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/drone-fusion", tags=["drone-fusion"])
ws_router = APIRouter(tags=["drone-fusion"])

# ---------------------------------------------------------------------------
# WebSocket broadcaster
# ---------------------------------------------------------------------------

_ws_subscribers: dict[str, set[WebSocket]] = defaultdict(set)
_ws_lock = asyncio.Lock()


async def _ws_broadcast(channel: str, payload: dict[str, Any]) -> None:
    async with _ws_lock:
        targets = set(_ws_subscribers.get(channel, set()))
    dead: set[WebSocket] = set()
    for ws in targets:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.add(ws)
    if dead:
        async with _ws_lock:
            _ws_subscribers[channel] -= dead


async def broadcast_fusion_event(payload: dict[str, Any]) -> None:
    await _ws_broadcast("drone-fusion", payload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(
    request: Request | WebSocket,
    action: str,
    *,
    user: UserAccount | None,
    resource_id: str,
    success: bool = True,
    detail: str | None = None,
) -> None:
    try:
        svc = get_audit_log_service()
        svc.record(
            action=action,
            user=user,
            resource_type="drone_fusion",
            resource_id=resource_id,
            success=success,
            detail=detail,
            request=request,
        )
    except Exception:
        pass


def _require_perm(user: UserAccount, perm: str, request: Request) -> None:
    rbac = get_rbac_config()
    if not has_permission(user.role, perm, rbac):
        _audit(request, "drone_fusion_access_denied", user=user, resource_id=perm, success=False)
        raise HTTPException(status_code=403, detail=f"Permission required: {perm}")


def _get_repos():
    from app.repositories.drone_fusion_repository import get_drone_fusion_repository
    from app.repositories.gis_repository import GisRepository
    return get_drone_fusion_repository(), GisRepository()


# ---------------------------------------------------------------------------
# Observation endpoints
# ---------------------------------------------------------------------------

@router.get("/observations", response_model=FusionObservationListResponse)
async def list_observations(
    request: Request,
    case_id: str | None = Query(None),
    event_id: str | None = Query(None),
    source_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionObservationListResponse:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    obs = repo.list_observations(case_id=case_id, event_id=event_id, source_type=source_type, limit=limit)
    return FusionObservationListResponse(observations=obs, total=len(obs))


# ---------------------------------------------------------------------------
# Correlation endpoints
# ---------------------------------------------------------------------------

@router.post("/correlate", response_model=FusionCorrelationListResponse)
async def run_correlation(
    request: Request,
    body: FusionCorrelateRequest,
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionCorrelationListResponse:
    _require_perm(user, "drone_fusion:write", request)
    repo, gis_repo = _get_repos()

    from app.services.drone_fusion.fusion_service import get_fusion_service
    from app.services.drone_fusion.observation_normalizer import normalize_fixed_camera_event

    svc = get_fusion_service(repo)

    obs_list = repo.list_observations(
        case_id=body.case_id,
        event_id=body.event_id,
        limit=500,
    )

    correlations = svc.correlate(
        observations=obs_list,
        user=user,
        case_id=body.case_id,
        event_id=body.event_id,
    )

    _audit(request, "drone_fusion_correlation_created", user=user, resource_id=body.case_id or "none",
           detail=f"created {len(correlations)} correlations")

    for corr in correlations:
        try:
            await broadcast_fusion_event({
                "event_type": "fusion_correlation_created",
                "correlation_id": corr.correlation_id,
                "confidence": corr.confidence,
                "operator_review_required": True,
                "safe_summary": corr.safe_summary,
            })
        except Exception:
            pass

    return FusionCorrelationListResponse(correlations=correlations, total=len(correlations))


@router.get("/correlations", response_model=FusionCorrelationListResponse)
async def list_correlations(
    request: Request,
    case_id: str | None = Query(None),
    event_id: str | None = Query(None),
    review_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionCorrelationListResponse:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    corrs = repo.list_correlations(case_id=case_id, event_id=event_id, review_status=review_status, limit=limit)
    return FusionCorrelationListResponse(correlations=corrs, total=len(corrs))


@router.get("/correlations/{correlation_id}", response_model=CrossSourceCorrelation)
async def get_correlation(
    correlation_id: str,
    request: Request,
    user: UserAccount = Depends(get_current_user_from_request),
) -> CrossSourceCorrelation:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    corr = repo.get_correlation(correlation_id)
    if corr is None:
        raise HTTPException(status_code=404, detail="Correlation not found")
    return corr


@router.post("/correlations/{correlation_id}/accept")
async def accept_correlation(
    correlation_id: str,
    request: Request,
    body: FusionReviewRequest | None = None,
    user: UserAccount = Depends(get_current_user_from_request),
) -> dict[str, Any]:
    _require_perm(user, "drone_fusion:review", request)
    repo, _ = _get_repos()
    review = FusionReviewRequest(action="accept", notes=body.notes if body else None)
    updated = repo.review_correlation(correlation_id, review, reviewed_by=user.username)
    if updated is None:
        raise HTTPException(status_code=404, detail="Correlation not found")
    _audit(request, "drone_fusion_correlation_reviewed", user=user, resource_id=correlation_id, detail="accepted")
    try:
        await broadcast_fusion_event({
            "event_type": "fusion_correlation_accepted",
            "correlation_id": correlation_id,
            "reviewed_by": user.username,
        })
    except Exception:
        pass
    return {"status": "accepted", "correlation_id": correlation_id}


@router.post("/correlations/{correlation_id}/reject")
async def reject_correlation(
    correlation_id: str,
    request: Request,
    body: FusionReviewRequest | None = None,
    user: UserAccount = Depends(get_current_user_from_request),
) -> dict[str, Any]:
    _require_perm(user, "drone_fusion:review", request)
    repo, _ = _get_repos()
    review = FusionReviewRequest(action="reject", notes=body.notes if body else None)
    updated = repo.review_correlation(correlation_id, review, reviewed_by=user.username)
    if updated is None:
        raise HTTPException(status_code=404, detail="Correlation not found")
    _audit(request, "drone_fusion_correlation_rejected", user=user, resource_id=correlation_id, detail="rejected")
    try:
        await broadcast_fusion_event({
            "event_type": "fusion_correlation_rejected",
            "correlation_id": correlation_id,
            "reviewed_by": user.username,
        })
    except Exception:
        pass
    return {"status": "rejected", "correlation_id": correlation_id}


@router.post("/correlations/{correlation_id}/inconclusive")
async def inconclusive_correlation(
    correlation_id: str,
    request: Request,
    body: FusionReviewRequest | None = None,
    user: UserAccount = Depends(get_current_user_from_request),
) -> dict[str, Any]:
    _require_perm(user, "drone_fusion:review", request)
    repo, _ = _get_repos()
    review = FusionReviewRequest(action="inconclusive", notes=body.notes if body else None)
    updated = repo.review_correlation(correlation_id, review, reviewed_by=user.username)
    if updated is None:
        raise HTTPException(status_code=404, detail="Correlation not found")
    _audit(request, "drone_fusion_correlation_reviewed", user=user, resource_id=correlation_id, detail="inconclusive")
    return {"status": "inconclusive", "correlation_id": correlation_id}


# ---------------------------------------------------------------------------
# Handoff endpoints
# ---------------------------------------------------------------------------

@router.get("/handoffs", response_model=FusionHandoffListResponse)
async def list_handoffs(
    request: Request,
    case_id: str | None = Query(None),
    event_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionHandoffListResponse:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    handoffs = repo.list_handoffs(case_id=case_id, event_id=event_id, limit=limit)
    return FusionHandoffListResponse(handoffs=handoffs, total=len(handoffs))


@router.post("/handoffs/suggest-for-event", response_model=FusionHandoffListResponse)
async def suggest_handoffs_for_event(
    request: Request,
    body: HandoffSuggestForEventRequest,
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionHandoffListResponse:
    _require_perm(user, "drone_fusion:write", request)
    repo, gis_repo = _get_repos()
    from app.services.drone_fusion.handoff_service import get_handoff_service
    svc = get_handoff_service(repository=repo, gis_repo=gis_repo)
    handoffs = svc.suggest_handoffs_for_event(
        event_id=body.event_id,
        user=user,
        radius_meters=body.radius_meters,
    )
    _audit(request, "drone_fusion_handoff_suggested", user=user, resource_id=body.event_id,
           detail=f"suggested {len(handoffs)} handoffs for event")
    try:
        for h in handoffs:
            await broadcast_fusion_event({
                "event_type": "fusion_handoff_suggested",
                "handoff_id": h.handoff_id,
                "from_source_type": h.from_source_type,
                "to_source_type": h.to_source_type,
                "confidence": h.confidence,
                "safe_summary": h.safe_summary,
            })
    except Exception:
        pass
    return FusionHandoffListResponse(handoffs=handoffs, total=len(handoffs))


@router.post("/handoffs/suggest-for-mission", response_model=FusionHandoffListResponse)
async def suggest_handoffs_for_mission(
    request: Request,
    body: HandoffSuggestForMissionRequest,
    user: UserAccount = Depends(get_current_user_from_request),
) -> FusionHandoffListResponse:
    _require_perm(user, "drone_fusion:write", request)
    repo, gis_repo = _get_repos()
    from app.services.drone_fusion.handoff_service import get_handoff_service
    svc = get_handoff_service(repository=repo, gis_repo=gis_repo)
    handoffs = svc.suggest_handoffs_for_mission(
        session_id=body.session_id,
        user=user,
        radius_meters=body.radius_meters,
    )
    _audit(request, "drone_fusion_handoff_suggested", user=user, resource_id=body.session_id,
           detail=f"suggested {len(handoffs)} handoffs for mission")
    return FusionHandoffListResponse(handoffs=handoffs, total=len(handoffs))


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

@router.get("/timeline")
async def get_fusion_timeline(
    request: Request,
    case_id: str | None = Query(None),
    event_id: str | None = Query(None),
    user: UserAccount = Depends(get_current_user_from_request),
) -> dict[str, Any]:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    timeline = repo.build_fusion_timeline(case_id=case_id, event_id=event_id)
    return timeline.model_dump()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def fusion_health(
    request: Request,
    user: UserAccount = Depends(get_current_user_from_request),
) -> dict[str, Any]:
    _require_perm(user, "drone_fusion:read", request)
    repo, _ = _get_repos()
    return repo.health_check()


# ---------------------------------------------------------------------------
# WebSocket /ws/drone-fusion
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/drone-fusion")
async def ws_drone_fusion(websocket: WebSocket) -> None:
    user = await authenticate_websocket(websocket, required_permission="drone_fusion:read")
    if user is None:
        await reject_ws(websocket, code=4401, reason="Authentication required")
        return

    await websocket.accept()
    async with _ws_lock:
        _ws_subscribers["drone-fusion"].add(websocket)

    try:
        await websocket.send_text(json.dumps({
            "event_type": "connected",
            "message": "Drone fusion WebSocket connected. Awaiting fusion events.",
        }))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"event_type": "ping"}))
            except (WebSocketDisconnect, BaseException):
                break
    finally:
        async with _ws_lock:
            _ws_subscribers["drone-fusion"].discard(websocket)
