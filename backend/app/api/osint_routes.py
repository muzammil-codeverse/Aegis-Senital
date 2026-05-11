from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.object_authorization import ensure_case_access, ensure_osint_source_access
from app.api.security_dependencies import require_permission as require_api_permission
from app.models.osint_models import (
    CaseEnrichmentSummaryRequest,
    CaseExternalSourceCreateRequest,
    CaseExternalSourceUpdateRequest,
)
from app.models.security_models import UserAccount
from app.security.upload_policy import get_upload_security_policy
from app.services.audit_log_service import get_audit_log_service
from app.services.osint_file_service import get_osint_file_service

router = APIRouter()


def _audit(request: Request, current_user: UserAccount, action: str, case_id: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        get_audit_log_service().record(
            action,
            user=current_user,
            resource_type="osint_enrichment",
            resource_id=case_id,
            detail=action.replace("_", " "),
            request=request,
            metadata=metadata or {},
        )
    except Exception:
        pass


def get_osint_service():
    from app.services.osint_service import get_osint_service as _service_getter

    return _service_getter()


def _get_osint_service():
    return get_osint_service()


def _require_case_source(case_id: str, source_id: str):
    source = _get_osint_service().get_source(source_id)
    if source is None or source.case_id != case_id:
        raise HTTPException(status_code=404, detail=f"Enrichment source '{source_id}' not found for case '{case_id}'")
    return source


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


@router.post("/api/cases/{case_id}/enrichment/sources")
def create_enrichment_source_api(
    case_id: str,
    body: CaseExternalSourceCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:write")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_osint_service()
    try:
        item = service.create_source(case_id, body, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "osint_source_created", case_id, {"source_id": item.source_id, "source_type": item.source_type})
    return {"item": item.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/enrichment/sources")
def list_enrichment_sources_api(
    case_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_osint_service()
    try:
        items = service.list_sources(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}


@router.get("/api/cases/{case_id}/enrichment/sources/{source_id}")
def get_enrichment_source_api(
    case_id: str,
    source_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:read")),
):
    ensure_case_access(request, current_user, case_id)
    ensure_osint_source_access(request, current_user, source_id)
    source = _require_case_source(case_id, source_id)
    return {"item": source.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/enrichment/sources/{source_id}/download")
def download_enrichment_source_api(
    case_id: str,
    source_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:read")),
):
    ensure_case_access(request, current_user, case_id)
    ensure_osint_source_access(request, current_user, source_id)
    source = _require_case_source(case_id, source_id)
    response = get_osint_file_service().build_download_response(case_id=case_id, source=source, user=current_user, request=request)
    _audit(request, current_user, "osint_source_file_downloaded", case_id, {"source_id": source_id})
    return response


@router.patch("/api/cases/{case_id}/enrichment/sources/{source_id}")
def update_enrichment_source_api(
    case_id: str,
    source_id: str,
    body: CaseExternalSourceUpdateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:write")),
):
    ensure_case_access(request, current_user, case_id)
    ensure_osint_source_access(request, current_user, source_id)
    _require_case_source(case_id, source_id)
    updates = {key: value for key, value in body.model_dump(exclude_none=True, mode="json").items() if key not in {"source_id", "case_id"}}
    try:
        item = _get_osint_service().update_source(source_id, updates, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Enrichment source '{source_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _audit(request, current_user, "osint_source_updated", case_id, {"source_id": source_id, "updated_fields": sorted(updates.keys())})
    return {"item": item.model_dump(mode="json"), "status": "ok"}


@router.delete("/api/cases/{case_id}/enrichment/sources/{source_id}")
def delete_enrichment_source_api(
    case_id: str,
    source_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:write")),
):
    ensure_case_access(request, current_user, case_id)
    ensure_osint_source_access(request, current_user, source_id)
    _require_case_source(case_id, source_id)
    deleted = _get_osint_service().delete_source(source_id, actor=current_user.username)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Enrichment source '{source_id}' not found")
    _audit(request, current_user, "osint_source_deleted", case_id, {"source_id": source_id})
    return {"item": {"source_id": source_id, "deleted": True}, "status": "ok"}


@router.post("/api/cases/{case_id}/enrichment/upload")
async def upload_enrichment_document_api(
    case_id: str,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    description: str = Form(default=""),
    source_reliability: str = Form(default="unknown"),
    metadata: str | None = Form(default=None),
    current_user: UserAccount = Depends(require_api_permission("osint:write")),
):
    ensure_case_access(request, current_user, case_id)
    content = await file.read()
    validation = get_upload_security_policy().validate(
        filename=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type,
        allowed_classes={"image", "document"},
    )
    service = _get_osint_service()
    try:
        source, upload = service.create_uploaded_source(
            case_id=case_id,
            filename=validation.normalized_filename,
            content=content,
            content_type=validation.content_type,
            title=title,
            description=description,
            source_reliability=source_reliability,
            metadata=_parse_metadata(metadata),
            actor=current_user.username,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(
        request,
        current_user,
        "osint_document_uploaded",
        case_id,
        {
            "source_id": source.source_id,
            "filename": upload["filename"],
            "sha256": validation.sha256,
            "size_bytes": validation.size_bytes,
            "media_class": validation.media_class,
        },
    )
    return {"item": {"source": source.model_dump(mode="json"), "upload": upload}, "status": "ok"}


@router.post("/api/cases/{case_id}/enrichment/links")
def add_enrichment_link_api(
    case_id: str,
    body: CaseExternalSourceCreateRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:write")),
):
    ensure_case_access(request, current_user, case_id)
    payload = body.model_copy(update={"source_type": "external_link"})
    service = _get_osint_service()
    try:
        item = service.create_source(case_id, payload, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "osint_link_added", case_id, {"source_id": item.source_id, "domain": (item.metadata or {}).get("domain")})
    return {"item": item.model_dump(mode="json"), "status": "ok"}


@router.post("/api/cases/{case_id}/enrichment/summarize")
def summarize_enrichment_api(
    case_id: str,
    body: CaseEnrichmentSummaryRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:summarize")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_osint_service()
    try:
        item = service.summarize(
            case_id,
            source_ids=body.source_ids,
            actor=current_user.username,
            operator_instructions=body.operator_instructions,
            escalate=body.escalate,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _audit(request, current_user, "osint_summary_generated", case_id, {"summary_id": item.summary_id, "source_count": len(item.source_ids)})
    return {"item": item.model_dump(mode="json"), "status": "ok"}


@router.get("/api/cases/{case_id}/enrichment/summaries")
def list_enrichment_summaries_api(
    case_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("osint:read")),
):
    ensure_case_access(request, current_user, case_id)
    service = _get_osint_service()
    try:
        items = service.list_summaries(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    payload = [item.model_dump(mode="json") for item in items]
    return {"items": payload, "count": len(payload), "status": "ok" if payload else "empty"}
