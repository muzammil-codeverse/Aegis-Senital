from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.object_authorization import ensure_case_access
from app.api.security_dependencies import require_permission as require_api_permission
from app.models.llm_models import (
    LlmEvidenceSummaryRequest,
    LlmQueryRequest,
    LlmReportRequest,
    LlmSummaryRequest,
    LlmTimelineSummaryRequest,
    LlmVerifyProviderRequest,
)
from app.models.security_models import UserAccount
from app.services.audit_log_service import get_audit_log_service

router = APIRouter()


def _audit(request: Request, current_user: UserAccount, action: str, metadata: dict | None = None) -> None:
    try:
        get_audit_log_service().record(
            action,
            user=current_user,
            resource_type="llm",
            resource_id=request.url.path,
            detail=action.replace("_", " "),
            request=request,
            metadata=metadata or {},
        )
    except Exception:
        pass


def get_llm_service():
    from app.services.llm_service import get_llm_service as _service_getter

    return _service_getter()


def _get_llm_service():
    return get_llm_service()


@router.get("/api/llm/status")
def get_llm_status_api(
    current_user: UserAccount = Depends(require_api_permission("llm:read")),
):
    return {"item": _get_llm_service().status(), "status": "ok"}


@router.post("/api/llm/verify-provider")
def verify_llm_provider_api(
    body: LlmVerifyProviderRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:write")),
):
    result = _get_llm_service().verify_provider(
        model_override=body.model,
        include_escalation=body.include_escalation,
        include_final_report=body.include_final_report,
    )
    _audit(
        request,
        current_user,
        "llm_provider_verification_requested",
        {
            "model": body.model,
            "include_escalation": body.include_escalation,
            "include_final_report": body.include_final_report,
            "result": result.get("status"),
        },
    )
    return {"item": result, "status": "ok" if result.get("status") == "ok" else "error"}


@router.post("/api/llm/cases/{case_id}/summary")
def summarize_case_api(
    case_id: str,
    body: LlmSummaryRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_llm_service()
    try:
        output = service.summarize_case(case_id, body, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "llm_case_summary_generated", {"case_id": case_id})
    return {"item": output.model_dump(mode="json"), "status": "ok"}


@router.post("/api/llm/cases/{case_id}/timeline-summary")
def summarize_timeline_api(
    case_id: str,
    body: LlmTimelineSummaryRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_llm_service()
    try:
        output = service.summarize_timeline(case_id, body.model_dump(mode="json"), actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "llm_timeline_summary_generated", {"case_id": case_id})
    return {"item": output.model_dump(mode="json"), "status": "ok"}


@router.post("/api/llm/cases/{case_id}/evidence-summary")
def summarize_evidence_api(
    case_id: str,
    body: LlmEvidenceSummaryRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_llm_service()
    try:
        output = service.summarize_evidence(case_id, body.model_dump(mode="json"), actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "llm_evidence_summary_generated", {"case_id": case_id, "evidence_ids": body.evidence_ids})
    return {"item": output.model_dump(mode="json"), "status": "ok"}


@router.post("/api/llm/cases/{case_id}/report")
def draft_report_api(
    case_id: str,
    body: LlmReportRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:report")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_llm_service()
    try:
        output = service.draft_report(case_id, body.model_dump(mode="json"), actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "llm_report_generated", {"case_id": case_id, "report_type": body.report_kind})
    return {"item": output.model_dump(mode="json"), "status": "ok"}


@router.post("/api/llm/cases/{case_id}/query")
def case_query_api(
    case_id: str,
    body: LlmQueryRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("llm:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_llm_service()
    try:
        output = service.answer_case_query(
            case_id,
            body.question,
            body.model_dump(mode="json"),
            actor=current_user.username,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "llm_case_query_generated", {"case_id": case_id})
    return {"item": output.model_dump(mode="json"), "status": "ok"}
