from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.security_dependencies import require_permission as require_api_permission
from app.models.case_models import (
    CaseCreateRequest,
    CaseEvidenceCreateRequest,
    CaseNoteCreateRequest,
    CaseUpdateRequest,
)
from app.models.security_models import UserAccount
from app.services.audit_log_service import get_audit_log_service
from app.services.case_service import get_case_service

router = APIRouter()


class CaseAssignRequest(BaseModel):
    assigned_to: str
    reason: str = ""


class CaseTransitionRequest(BaseModel):
    reason: str = ""


def _audit_write(request: Request, current_user: UserAccount | None, action: str, case_id: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        get_audit_log_service().record(
            action,
            user=current_user,
            resource_type="case",
            resource_id=case_id,
            detail=action.replace("_", " "),
            request=request,
            metadata=metadata or {},
        )
    except Exception:
        pass


@router.post("/api/cases")
def create_case_api(
    body: CaseCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = get_case_service()
    try:
        case = service.create_case(body, actor=current_user.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit_write(request, current_user, "case_created", case.case_id, {"source": "manual"})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases")
def list_cases_api(
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    camera: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    source_event_id: str | None = Query(default=None),
    requires_review: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    service = get_case_service()
    items = service.list_cases(
        {
            "status": status,
            "priority": priority,
            "severity": severity,
            "camera": camera,
            "tag": tag,
            "assigned_to": assigned_to,
            "source_event_id": source_event_id,
            "requires_review": requires_review,
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
            "limit": limit,
        }
    )
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.get("/api/cases/{case_id}")
def get_case_api(
    case_id: str,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    service = get_case_service()
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    evidence = service.list_evidence(case_id)
    timeline = service.get_timeline(case_id)
    return {
        "item": case.model_dump(mode="json"),
        "references": {
            "evidence_ids": [item.evidence_id for item in evidence],
            "timeline_ids": [item.timeline_id for item in timeline],
            "source_event_ids": list(case.source_event_ids),
        },
        "status": "ok",
    }


@router.patch("/api/cases/{case_id}")
def update_case_api(
    case_id: str,
    body: CaseUpdateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = get_case_service()
    try:
        case = service.update_case(case_id, body, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit_write(request, current_user, "case_updated", case_id, {"updated_fields": sorted(body.model_dump(exclude_none=True).keys())})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.delete("/api/cases/{case_id}")
def delete_or_archive_case_api(
    case_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:close")),
):
    service = get_case_service()
    try:
        case = service.delete_or_archive_case(case_id, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    _audit_write(request, current_user, "case_archived", case_id, {"source": "delete_route"})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/from-event/{event_id}")
def create_case_from_event_api(
    event_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = get_case_service()
    try:
        case = service.create_case_from_event_id(event_id, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' was not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit_write(request, current_user, "case_created_from_event", case.case_id, {"event_id": event_id})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/evidence")
def add_case_evidence_api(
    case_id: str,
    body: CaseEvidenceCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = get_case_service()
    try:
        evidence = service.add_evidence(case_id, body, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit_write(request, current_user, "case_evidence_added", case_id, {"evidence_id": evidence.evidence_id})
    return {"item": evidence.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/evidence")
def list_case_evidence_api(
    case_id: str,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    service = get_case_service()
    try:
        items = service.list_evidence(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.post("/api/cases/{case_id}/notes")
def add_case_note_api(
    case_id: str,
    body: CaseNoteCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = get_case_service()
    try:
        note = service.add_note(case_id, body, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit_write(request, current_user, "case_note_added", case_id, {"note_id": note.note_id})
    return {"item": note.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/notes")
def list_case_notes_api(
    case_id: str,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    service = get_case_service()
    try:
        items = service.list_notes(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.post("/api/cases/{case_id}/assign")
def assign_case_api(
    case_id: str,
    body: CaseAssignRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:assign")),
):
    service = get_case_service()
    try:
        case = service.assign_case(case_id, body.assigned_to, actor=current_user.username, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    _audit_write(request, current_user, "case_assigned", case_id, {"assigned_to": body.assigned_to})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/close")
def close_case_api(
    case_id: str,
    request: Request,
    body: CaseTransitionRequest = Body(default_factory=CaseTransitionRequest),
    current_user: UserAccount = Depends(require_api_permission("case:close")),
):
    service = get_case_service()
    try:
        case = service.close_case(case_id, actor=current_user.username, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_closed", case_id, {})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/reopen")
def reopen_case_api(
    case_id: str,
    request: Request,
    body: CaseTransitionRequest = Body(default_factory=CaseTransitionRequest),
    current_user: UserAccount = Depends(require_api_permission("case:close")),
):
    service = get_case_service()
    try:
        case = service.reopen_case(case_id, actor=current_user.username, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_reopened", case_id, {})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/dismiss")
def dismiss_case_api(
    case_id: str,
    body: CaseTransitionRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:close")),
):
    service = get_case_service()
    try:
        case = service.dismiss_case(case_id, actor=current_user.username, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_dismissed", case_id, {})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/archive")
def archive_case_api(
    case_id: str,
    request: Request,
    body: CaseTransitionRequest = Body(default_factory=CaseTransitionRequest),
    current_user: UserAccount = Depends(require_api_permission("case:close")),
):
    service = get_case_service()
    try:
        case = service.archive_case(case_id, actor=current_user.username, reason=body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_archived", case_id, {})
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/timeline")
def get_case_timeline_api(
    case_id: str,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    service = get_case_service()
    try:
        items = service.get_timeline(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.get("/api/cases/{case_id}/export")
def export_case_api(
    case_id: str,
    request: Request,
    format: str = Query(default="json"),
    current_user: UserAccount = Depends(require_api_permission("case:export")),
):
    service = get_case_service()
    try:
        export = service.export_case(case_id, format=format, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_exported", case_id, {"format": format})
    return {"item": export.model_dump(mode="json"), "status": "ok"}
