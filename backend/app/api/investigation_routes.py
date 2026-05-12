from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.security_dependencies import require_permission
from app.models.investigation_models import (
    HypothesisReviewRequest,
    PathReconstructionRequest,
)
from app.models.security_models import AuditAction, UserAccount
from app.repositories.gis_repository import get_gis_repository
from app.repositories.investigation_repository import get_investigation_repository
from app.services.audit_log_service import get_audit_log_service
from app.services.camera_graph_service import build_camera_graph, camera_graph_to_dict
from app.services.path_reconstruction_service import reconstruct_path
from inference.metrics import metrics

router = APIRouter(tags=["investigation"])


def _t0() -> float:
    return time.perf_counter()


def _record_latency(start: float) -> None:
    try:
        ms = int((time.perf_counter() - start) * 1000)
        metrics.set_value("investigation_path_generation_latency_ms", ms)
    except Exception:
        pass


@router.post("/api/investigation/path-reconstruction")
def post_path_reconstruction(
    request: Request,
    body: PathReconstructionRequest,
    current_user: UserAccount = Depends(require_permission("investigation:write")),
):
    t = _t0()
    gis_repo = get_gis_repository()
    inv_repo = get_investigation_repository()
    response = reconstruct_path(body, gis_repo, inv_repo, current_user)
    get_audit_log_service().record(
        AuditAction.INVESTIGATION_PATH_RECONSTRUCTED,
        user=current_user,
        resource_type="investigation",
        resource_id=response.request_id,
        detail=f"Path reconstruction status={response.status} hypotheses={len(response.hypotheses)}",
        request=request,
    )
    _record_latency(t)
    return {"item": response.model_dump(mode="json"), "status": "ok"}


@router.get("/api/investigation/hypotheses")
def list_hypotheses(
    request: Request,
    current_user: UserAccount = Depends(require_permission("investigation:read")),
    case_id: str | None = None,
    subject_ref_id: str | None = None,
):
    del request
    inv_repo = get_investigation_repository()
    items = inv_repo.list_hypotheses(case_id=case_id, subject_ref_id=subject_ref_id)
    return {"items": [i.model_dump(mode="json") for i in items], "count": len(items), "status": "ok"}


@router.get("/api/investigation/hypotheses/{hypothesis_id}")
def get_hypothesis(
    request: Request,
    hypothesis_id: str,
    current_user: UserAccount = Depends(require_permission("investigation:read")),
):
    del request, current_user
    inv_repo = get_investigation_repository()
    hyp = inv_repo.get_hypothesis(hypothesis_id)
    if hyp is None:
        return {"item": None, "status": "not_found"}
    return {"item": hyp.model_dump(mode="json"), "status": "ok"}


def _review_endpoint(
    request: Request,
    hypothesis_id: str,
    review_status: str,
    current_user: UserAccount,
    reviewer_notes: str | None = None,
):
    body = HypothesisReviewRequest(review_status=review_status, reviewer_notes=reviewer_notes)  # type: ignore[arg-type]
    inv_repo = get_investigation_repository()
    updated, record = inv_repo.review_hypothesis(hypothesis_id, body, current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    audit_action = (
        AuditAction.INVESTIGATION_HYPOTHESIS_REJECTED
        if review_status == "rejected"
        else AuditAction.INVESTIGATION_HYPOTHESIS_REVIEWED
    )
    get_audit_log_service().record(
        audit_action,
        user=current_user,
        resource_type="hypothesis",
        resource_id=hypothesis_id,
        detail=f"Hypothesis reviewed: {review_status}",
        request=request,
    )
    try:
        if review_status == "rejected":
            metrics.increment("investigation_hypotheses_rejected_total")
        elif review_status == "accepted":
            metrics.increment("investigation_hypotheses_accepted_total")
    except Exception:
        pass
    return {
        "item": updated.model_dump(mode="json"),
        "review": record.model_dump(mode="json") if record else None,
        "status": "ok",
    }


@router.post("/api/investigation/hypotheses/{hypothesis_id}/accept")
def accept_hypothesis(
    request: Request,
    hypothesis_id: str,
    current_user: UserAccount = Depends(require_permission("investigation:write")),
):
    return _review_endpoint(request, hypothesis_id, "accepted", current_user)


@router.post("/api/investigation/hypotheses/{hypothesis_id}/reject")
def reject_hypothesis(
    request: Request,
    hypothesis_id: str,
    current_user: UserAccount = Depends(require_permission("investigation:write")),
):
    return _review_endpoint(request, hypothesis_id, "rejected", current_user)


@router.post("/api/investigation/hypotheses/{hypothesis_id}/inconclusive")
def mark_hypothesis_inconclusive(
    request: Request,
    hypothesis_id: str,
    current_user: UserAccount = Depends(require_permission("investigation:write")),
):
    return _review_endpoint(request, hypothesis_id, "inconclusive", current_user)


@router.get("/api/investigation/cases/{case_id}/timeline")
def get_case_timeline(
    request: Request,
    case_id: str,
    current_user: UserAccount = Depends(require_permission("investigation:read")),
):
    del request, current_user
    inv_repo = get_investigation_repository()
    timeline = inv_repo.build_case_timeline(case_id)
    return {"item": timeline.model_dump(mode="json"), "status": "ok"}


@router.get("/api/investigation/cameras/graph")
def get_camera_graph(
    request: Request,
    current_user: UserAccount = Depends(require_permission("investigation:read")),
):
    del request
    gis_repo = get_gis_repository()
    nodes, edges = build_camera_graph(gis_repo, current_user)
    return {"item": camera_graph_to_dict(nodes, edges), "status": "ok"}
