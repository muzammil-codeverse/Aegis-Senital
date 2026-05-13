from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.api.object_authorization import (
    can_access_uploaded_video_session,
    ensure_uploaded_video_session_access,
)
from app.api.security_dependencies import require_permission
from app.api.websocket_security import authenticate_websocket, reject_ws
from app.models.security_models import AuditAction, UserAccount
from app.models.uploaded_video_models import UploadedVideoCaseCreationRequest, UploadedVideoProcessingOptions
from app.services.audit_log_service import get_audit_log_service
from app.services.uploaded_video_service import get_uploaded_video_service


router = APIRouter()


def _audit(
    request: Request,
    action: AuditAction,
    *,
    user: UserAccount,
    session_id: str,
    detail: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    get_audit_log_service().record(
        action,
        user=user,
        resource_type="uploaded_video",
        resource_id=session_id,
        detail=detail,
        request=request,
        metadata=metadata or {},
    )


def _parse_options(raw: str | None) -> UploadedVideoProcessingOptions:
    if not raw:
        return UploadedVideoProcessingOptions()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid uploaded-video options JSON: {exc}") from exc
    return UploadedVideoProcessingOptions.model_validate(payload)


@router.get("/api/uploaded-videos")
def list_uploaded_videos_api(
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    del request
    service = get_uploaded_video_service()
    if current_user.role in {"admin", "supervisor"}:
        items = service.list_sessions()
    else:
        items = service.list_sessions(created_by=current_user.user_id) + [
            session
            for session in service.list_sessions(created_by=current_user.username)
            if session.created_by != current_user.user_id
        ]
    return {"items": [item.model_dump(mode="json") for item in items], "count": len(items), "status": "ok" if items else "empty"}


@router.post("/api/uploaded-videos")
async def upload_video_api(
    request: Request,
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
    current_user: UserAccount = Depends(require_permission("uploaded_video:write")),
):
    service = get_uploaded_video_service()
    response = service.upload_video(file, _parse_options(options), current_user)
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_UPLOADED,
        user=current_user,
        session_id=response.session.session_id,
        detail="Uploaded video stored under managed storage.",
        metadata={"filename": response.session.original_filename},
    )
    return response.model_dump(mode="json")


@router.get("/api/uploaded-videos/{session_id}")
def get_uploaded_video_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    session = get_uploaded_video_service().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Uploaded-video session '{session_id}' not found")
    return {"item": session.model_dump(mode="json"), "status": "ok"}


@router.post("/api/uploaded-videos/{session_id}/process")
def process_uploaded_video_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:process")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    status = get_uploaded_video_service().start_processing(session_id, current_user)
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_PROCESSING_STARTED,
        user=current_user,
        session_id=session_id,
        detail="Uploaded-video processing started.",
    )
    return {"item": status.model_dump(mode="json"), "status": "ok"}


@router.get("/api/uploaded-videos/{session_id}/status")
def uploaded_video_status_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    status = get_uploaded_video_service().get_status(session_id, current_user)
    return {"item": status.model_dump(mode="json"), "status": "ok"}


@router.get("/api/uploaded-videos/{session_id}/timeline")
def uploaded_video_timeline_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    items = get_uploaded_video_service().get_timeline(session_id, current_user)
    return {"items": [item.model_dump(mode="json") for item in items], "count": len(items), "status": "ok" if items else "empty"}


@router.get("/api/uploaded-videos/{session_id}/events")
def uploaded_video_events_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    items = get_uploaded_video_service().get_events(session_id, current_user)
    return {"items": [item.model_dump(mode="json") for item in items], "count": len(items), "status": "ok" if items else "empty"}


@router.post("/api/uploaded-videos/{session_id}/cancel")
def cancel_uploaded_video_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:process")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    status = get_uploaded_video_service().cancel_processing(session_id, current_user)
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_CANCELLED,
        user=current_user,
        session_id=session_id,
        detail="Uploaded-video processing cancelled.",
    )
    return {"item": status.model_dump(mode="json"), "status": "ok"}


@router.post("/api/uploaded-videos/{session_id}/create-case")
def create_case_from_uploaded_video_api(
    session_id: str,
    request: Request,
    body: UploadedVideoCaseCreationRequest,
    current_user: UserAccount = Depends(require_permission("uploaded_video:case")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    case = get_uploaded_video_service().create_case_from_session(session_id, body, current_user)
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_CASE_CREATED,
        user=current_user,
        session_id=session_id,
        detail="Created case from uploaded-video session.",
        metadata={"case_id": case.case_id},
    )
    return {"item": case.model_dump(mode="json"), "status": "ok"}


@router.get("/api/uploaded-videos/{session_id}/clips/{event_id}/download")
def download_uploaded_video_clip_api(
    session_id: str,
    event_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    service = get_uploaded_video_service()
    try:
        clip_path = service.resolve_event_clip_path(session_id, event_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Uploaded-video session or clip directory not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not clip_path.is_file():
        raise HTTPException(status_code=404, detail="Replay clip not found for this event")
    events = service.get_events(session_id, current_user)
    target = next((item for item in events if item.event_id == event_id), None)
    if target is None or target.replay_clip is None:
        raise HTTPException(status_code=404, detail="Replay clip metadata not available for this event")
    digest = target.replay_clip.hash_sha256
    from app.services.evidence_integrity import compute_sha256

    if digest and compute_sha256(str(clip_path)) != digest:
        raise HTTPException(status_code=409, detail="Replay clip failed integrity verification")
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_CLIP_DOWNLOADED,
        user=current_user,
        session_id=session_id,
        detail="Downloaded uploaded-video replay clip.",
        metadata={"event_id": event_id, "clip_id": target.replay_clip.clip_id},
    )
    filename = f"{event_id}.mp4"
    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/uploaded-videos/{session_id}/report")
def uploaded_video_report_api(
    session_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_permission("uploaded_video:read")),
):
    ensure_uploaded_video_session_access(request, current_user, session_id)
    report = get_uploaded_video_service().get_report(session_id, current_user)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Uploaded-video report for '{session_id}' not found")
    _audit(
        request,
        AuditAction.UPLOADED_VIDEO_REPORT_VIEWED,
        user=current_user,
        session_id=session_id,
        detail="Viewed uploaded-video report.",
    )
    return {"item": report.model_dump(mode="json"), "status": "ok"}


@router.websocket("/ws/uploaded-video/{session_id}")
async def uploaded_video_progress_ws(websocket: WebSocket, session_id: str):
    user = await authenticate_websocket(websocket, required_permission="uploaded_video:read")
    if user is None:
        return
    if not can_access_uploaded_video_session(user, session_id):
        await reject_ws(websocket, reason="Access denied for uploaded-video session")
        return
    await websocket.accept()
    service = get_uploaded_video_service()
    try:
        while True:
            status = service.get_status(session_id, user)
            await websocket.send_json(status.model_dump(mode="json"))
            if status.status in {"completed", "failed", "cancelled"} and not status.active:
                break
            await asyncio.sleep(1.0)
    except BaseException:
        return
