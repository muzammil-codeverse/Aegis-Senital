from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.api.security_dependencies import (
    get_current_user_from_request,
    require_permission as require_api_permission,
)
from app.models.security_models import AuditAction, UserAccount
from app.models.streaming_models import ReplayClipRequest, WebRTCOfferRequest
from app.services.audit_log_service import get_audit_log_service
from app.services.hls_service import get_hls_service
from app.services.replay_clip_service import get_replay_clip_service
from app.services.stream_session_manager import get_stream_session_manager
from app.services.webrtc_service import get_webrtc_service

router = APIRouter()


def _audit(
    request: Request,
    action: AuditAction,
    *,
    resource_type: str,
    resource_id: str,
    detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        get_audit_log_service().record(
            action,
            user=get_current_user_from_request(request),
            resource_type=resource_type,
            resource_id=resource_id,
            success=True,
            detail=detail,
            request=request,
            metadata=metadata,
        )
    except Exception:
        pass


def _mjpeg_boundary_chunk(image_bytes: bytes) -> bytes:
    boundary = b"--aegisstream\r\n"
    header = (
        b"Content-Type: image/jpeg\r\n"
        + b"Content-Length: "
        + str(len(image_bytes)).encode()
        + b"\r\n\r\n"
    )
    return boundary + header + image_bytes + b"\r\n"


@router.get("/api/streams/{camera_id}/health")
def get_stream_health_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    health = get_stream_session_manager().get_stream_health(camera_id)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="Stream health viewed")
    return {"item": health, "status": "ok"}


@router.get("/api/streams")
def list_streams_api(
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    items = get_stream_session_manager().list_stream_states()
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id="*", detail="Stream inventory viewed")
    return {"items": items, "status": "ok"}


@router.get("/api/streams/{camera_id}/stats")
def get_stream_stats_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    stats = get_stream_session_manager().get_stream_stats(camera_id)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="Stream stats viewed")
    return {"item": stats, "status": "ok"}


@router.post("/api/streams/{camera_id}/start")
def start_stream_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:write")),
):
    result = get_stream_session_manager().start_stream(camera_id)
    processor = get_stream_session_manager().get_stream_processor(camera_id)
    if processor is not None:
        get_hls_service().ensure_preview(camera_id, getattr(processor, "source", None))
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=camera_id, detail="Stream start requested")
    return {"item": result, "status": "ok"}


@router.post("/api/streams/{camera_id}/stop")
async def stop_stream_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:write")),
):
    await get_webrtc_service().stop(camera_id)
    get_hls_service().stop_preview(camera_id)
    result = get_stream_session_manager().stop_stream(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=camera_id, detail="Stream stop requested")
    return {"item": result, "status": "ok"}


@router.post("/api/streams/{camera_id}/restart")
async def restart_stream_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:write")),
):
    await get_webrtc_service().stop(camera_id)
    get_hls_service().stop_preview(camera_id)
    result = get_stream_session_manager().restart_stream(camera_id)
    processor = get_stream_session_manager().get_stream_processor(camera_id)
    if processor is not None:
        get_hls_service().ensure_preview(camera_id, getattr(processor, "source", None))
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=camera_id, detail="Stream restart requested")
    return {"item": result, "status": "ok"}


@router.post("/api/streams/{camera_id}/webrtc/offer")
async def stream_webrtc_offer_api(
    camera_id: str,
    body: WebRTCOfferRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    answer = await get_webrtc_service().handle_offer(camera_id, body)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="WebRTC preview offer handled")
    return {"item": answer.model_dump(mode="json"), "status": answer.status}


@router.post("/api/streams/{camera_id}/webrtc/stop")
async def stream_webrtc_stop_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:write")),
):
    result = await get_webrtc_service().stop(camera_id)
    _audit(request, AuditAction.CAMERA_CONTROLLED, resource_type="stream", resource_id=camera_id, detail="WebRTC preview stopped")
    return {"item": result, "status": "ok"}


@router.get("/api/streams/{camera_id}/webrtc/status")
def stream_webrtc_status_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    status = get_webrtc_service().get_status(camera_id)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="WebRTC preview status viewed")
    return {"item": status, "status": "ok"}


@router.get("/api/streams/{camera_id}/hls/playlist.m3u8")
def stream_hls_playlist_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    processor = get_stream_session_manager().get_stream_processor(camera_id)
    get_hls_service().ensure_preview(camera_id, getattr(processor, "source", None) if processor is not None else None)
    playlist_path = get_hls_service().resolve_playlist_path(camera_id)
    if not playlist_path.exists():
        info = get_hls_service().get_playlist_info(camera_id)
        return JSONResponse(status_code=503, content={"item": info.model_dump(mode="json"), "status": "unavailable"})
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="HLS playlist viewed")
    return FileResponse(str(playlist_path), media_type="application/vnd.apple.mpegurl")


@router.get("/api/streams/{camera_id}/hls/{segment_name}")
def stream_hls_segment_api(
    camera_id: str,
    segment_name: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    try:
        path = get_hls_service().resolve_segment_path(camera_id, segment_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not path.exists():
        raise HTTPException(status_code=404, detail="HLS segment not found")
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="HLS segment viewed")
    return FileResponse(str(path), media_type="video/mp2t")


@router.post("/api/streams/{camera_id}/replay/export")
def stream_replay_export_api(
    camera_id: str,
    body: ReplayClipRequest,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:replay")),
):
    clip = get_replay_clip_service().export_clip(camera_id, body, actor=current_user.username)
    _audit(
        request,
        AuditAction.FORENSIC_REPLAY_VIEWED,
        resource_type="stream_replay",
        resource_id=f"{camera_id}:{clip.clip_id}",
        detail="Replay clip exported",
        metadata={"case_id": body.case_id, "event_id": body.event_id, "status": clip.status},
    )
    return {"item": clip.model_dump(mode="json"), "status": clip.status}


@router.get("/api/streams/{camera_id}/replay/{clip_id}")
def stream_replay_get_api(
    camera_id: str,
    clip_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:replay")),
):
    try:
        path = get_replay_clip_service().resolve_clip_path(camera_id, clip_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Replay clip not found")
    _audit(request, AuditAction.FORENSIC_REPLAY_VIEWED, resource_type="stream_replay", resource_id=f"{camera_id}:{clip_id}")
    return FileResponse(str(path), media_type="video/mp4", filename=path.name)


@router.get("/api/streams/{camera_id}/mjpeg")
async def stream_mjpeg_api(
    camera_id: str,
    request: Request,
    current_user: UserAccount = Depends(require_api_permission("stream:read")),
):
    processor = get_stream_session_manager().get_stream_processor(camera_id)
    if processor is None:
        return JSONResponse(status_code=404, content={"status": "not_found", "detail": "stream is not running"})

    processor.increment_preview_clients(1)
    _audit(request, AuditAction.CAMERA_VIEWED, resource_type="stream", resource_id=camera_id, detail="Direct MJPEG preview opened")

    async def _generate():
        try:
            while True:
                image_bytes, _ = processor.get_preview_frame_jpeg()
                if image_bytes:
                    yield _mjpeg_boundary_chunk(image_bytes)
                else:
                    yield b"--aegisstream\r\n\r\n"
                await asyncio.sleep(0.1)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            processor.increment_preview_clients(-1)

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=aegisstream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Stream-Opened-At": datetime.now(timezone.utc).isoformat(),
        },
    )
