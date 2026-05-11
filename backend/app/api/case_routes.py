from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.api.object_authorization import (
    can_access_case,
    ensure_camera_access,
    ensure_case_access,
    ensure_evidence_access,
    ensure_event_payload_access,
)
from app.api.security_dependencies import require_permission as require_api_permission
from app.models.case_models import (
    CaseCreateRequest,
    CaseEvidenceCreateRequest,
    CaseNoteCreateRequest,
    CaseUpdateRequest,
)
from app.models.security_models import UserAccount
from app.services.audit_log_service import get_audit_log_service
from app.services.evidence_file_service import get_evidence_file_service

router = APIRouter()


class CaseAssignRequest(BaseModel):
    assigned_to: str
    reason: str = ""


class CaseTransitionRequest(BaseModel):
    reason: str = ""


def get_case_service():
    from app.services.case_service import get_case_service as _service_getter

    return _service_getter()


def _get_case_service():
    return get_case_service()


def _resolve_event_payload(event_id: str) -> dict[str, Any] | None:
    return _get_case_service().resolve_event_by_id(event_id)


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


def _parse_metadata(raw_metadata: str | None) -> dict[str, Any]:
    text = str(raw_metadata or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return payload


def _parse_track_ids(raw_track_ids: str | None) -> list[str]:
    text = str(raw_track_ids or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="track_ids must be valid JSON or comma-separated text") from exc
        if not isinstance(payload, list):
            raise HTTPException(status_code=400, detail="track_ids JSON must be an array")
        return [str(item).strip() for item in payload if str(item).strip()]
    return [item.strip() for item in text.split(",") if item.strip()]


def _audit_access_denied(request: Request, current_user: UserAccount | None, case_id: str, evidence_id: str | None = None) -> None:
    try:
        get_audit_log_service().record(
            "case_evidence_access_denied",
            user=current_user,
            resource_type="case_evidence",
            resource_id=evidence_id or case_id,
            success=False,
            detail="case evidence access denied",
            request=request,
            metadata={"case_id": case_id, "evidence_id": evidence_id},
        )
    except Exception:
        pass


@router.post("/api/cases")
def create_case_api(
    body: CaseCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    service = _get_case_service()
    for camera_id in body.camera_ids:
        ensure_camera_access(request, current_user, camera_id)
    for event_id in body.source_event_ids:
        payload = _resolve_event_payload(event_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Event '{event_id}' was not found")
        ensure_event_payload_access(
            request,
            current_user,
            resource_id=event_id,
            payload=(payload.get("payload") if isinstance(payload, dict) else None) or payload,
        )
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
    service = _get_case_service()
    items = [
        item
        for item in service.list_cases(
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
        if can_access_case(current_user, item.case_id)
    ]
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.get("/api/cases/{case_id}")
def get_case_api(
    case_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    evidence = service.list_evidence(case_id)
    timeline = service.get_timeline(case_id)
    enrichment_sources: list[dict[str, Any]] = []
    enrichment_summaries: list[dict[str, Any]] = []
    try:
        from app.services.osint_service import get_osint_service

        osint_service = get_osint_service()
        if osint_service.health().get("enabled", False):
            enrichment_sources = [item.model_dump(mode="json") for item in osint_service.list_sources(case_id)]
            enrichment_summaries = [item.model_dump(mode="json") for item in osint_service.list_summaries(case_id)]
    except Exception:
        enrichment_sources = []
        enrichment_summaries = []
    return {
        "item": case.model_dump(mode="json"),
        "enrichment": {
            "sources": enrichment_sources,
            "summaries": enrichment_summaries,
        },
        "references": {
            "evidence_ids": [item.evidence_id for item in evidence],
            "timeline_ids": [item.timeline_id for item in timeline],
            "source_event_ids": list(case.source_event_ids),
            "enrichment_source_ids": [item.get("source_id") for item in enrichment_sources],
            "enrichment_summary_ids": [item.get("summary_id") for item in enrichment_summaries],
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    service = _get_case_service()
    payload = service.resolve_event_by_id(event_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' was not found")
    ensure_event_payload_access(
        request,
        current_user,
        resource_id=event_id,
        payload=(payload.get("payload") if isinstance(payload, dict) else None) or payload,
    )
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
    ensure_case_access(request, current_user, case_id)
    if body.camera_id:
        ensure_camera_access(request, current_user, body.camera_id)
    if body.source_event_id:
        payload = _resolve_event_payload(body.source_event_id)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"Event '{body.source_event_id}' was not found")
        ensure_event_payload_access(
            request,
            current_user,
            resource_id=body.source_event_id,
            payload=(payload.get("payload") if isinstance(payload, dict) else None) or payload,
        )
    service = _get_case_service()
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
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
    try:
        items = service.list_evidence(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.post("/api/cases/{case_id}/evidence/upload")
def upload_case_evidence_file_api(
    case_id: str,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    evidence_type: str | None = Form(default=None),
    source_event_id: str | None = Form(default=None),
    camera_id: str | None = Form(default=None),
    track_ids: str | None = Form(default=None),
    metadata: str | None = Form(default=None),
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    try:
        ensure_case_access(request, current_user, case_id)
    except HTTPException:
        _audit_access_denied(request, current_user, case_id)
        raise
    payload = _parse_metadata(metadata)
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if evidence_type:
        payload["evidence_type"] = evidence_type
    if source_event_id:
        payload["source_event_id"] = source_event_id
    if camera_id:
        ensure_camera_access(request, current_user, camera_id)
        payload["camera_id"] = camera_id
    elif payload.get("camera_id"):
        ensure_camera_access(request, current_user, str(payload.get("camera_id")))
    parsed_track_ids = _parse_track_ids(track_ids)
    if parsed_track_ids:
        payload["track_ids"] = parsed_track_ids
    if source_event_id:
        resolved = _resolve_event_payload(source_event_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"Event '{source_event_id}' was not found")
        ensure_event_payload_access(
            request,
            current_user,
            resource_id=source_event_id,
            payload=(resolved.get("payload") if isinstance(resolved, dict) else None) or resolved,
        )
    elif payload.get("source_event_id"):
        resolved = _resolve_event_payload(str(payload["source_event_id"]))
        if resolved is None:
            raise HTTPException(status_code=404, detail=f"Event '{payload['source_event_id']}' was not found")
        ensure_event_payload_access(
            request,
            current_user,
            resource_id=str(payload["source_event_id"]),
            payload=(resolved.get("payload") if isinstance(resolved, dict) else None) or resolved,
        )
    try:
        evidence = get_evidence_file_service().upload_case_evidence_file(case_id, file, payload, current_user, request=request)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    _audit_write(request, current_user, "case_evidence_file_uploaded", case_id, {"evidence_id": evidence.evidence_id})
    return {"item": evidence.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/evidence/manifest")
def get_case_evidence_manifest_api(
    case_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:export")),
):
    try:
        ensure_case_access(request, current_user, case_id)
    except HTTPException:
        _audit_access_denied(request, current_user, case_id)
        raise
    try:
        manifest = get_evidence_file_service().build_evidence_manifest(case_id, current_user, request=request)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return {"item": manifest.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/evidence/{evidence_id}/download")
def download_case_evidence_file_api(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    try:
        ensure_case_access(request, current_user, case_id)
        ensure_evidence_access(request, current_user, evidence_id)
    except HTTPException:
        _audit_access_denied(request, current_user, case_id, evidence_id)
        raise
    return get_evidence_file_service().get_case_evidence_file(case_id, evidence_id, current_user, request=request)


@router.post("/api/cases/{case_id}/evidence/{evidence_id}/verify")
def verify_case_evidence_file_api(
    case_id: str,
    evidence_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    try:
        ensure_case_access(request, current_user, case_id)
        ensure_evidence_access(request, current_user, evidence_id)
    except HTTPException:
        _audit_access_denied(request, current_user, case_id, evidence_id)
        raise
    result = get_evidence_file_service().verify_case_evidence_file(case_id, evidence_id, current_user, request=request)
    return {"item": result.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/notes")
def add_case_note_api(
    case_id: str,
    body: CaseNoteCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("case:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
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
    ensure_case_access(request, current_user, case_id)
    service = _get_case_service()
    try:
        export = service.export_case(case_id, format=format, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_write(request, current_user, "case_exported", case_id, {"format": format})
    return {"item": export.model_dump(mode="json"), "status": "ok"}
