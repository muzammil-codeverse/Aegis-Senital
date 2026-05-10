from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction

import cv2
import numpy as np

from app.models.streaming_models import StreamPreviewSession, WebRTCAnswerResponse, WebRTCOfferRequest
from app.services.rtsp_ingest_service import load_streaming_runtime_config
from app.services.stream_session_manager import get_stream_session_manager

logger = logging.getLogger(__name__)

AIORTC_AVAILABLE = False
AIORTC_IMPORT_ERROR: str | None = None
VideoStreamTrack = object
RTCPeerConnection = object
RTCSessionDescription = object
RTCConfiguration = object
RTCIceServer = object
VideoFrame = object

try:
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from av import VideoFrame

    AIORTC_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency
    AIORTC_IMPORT_ERROR = str(exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _PreviewSessionRecord:
    camera_id: str
    session_id: str
    started_at: str
    last_seen_at: str
    status: str
    detail: str | None = None
    pc: object | None = None
    processor: object | None = None


if AIORTC_AVAILABLE:  # pragma: no branch
    class LatestPreviewTrack(VideoStreamTrack):  # type: ignore[misc]
        kind = "video"

        def __init__(self, processor, frame_interval_seconds: float) -> None:
            super().__init__()
            self._processor = processor
            self._frame_interval_seconds = max(0.03, frame_interval_seconds)

        async def recv(self):
            await asyncio.sleep(self._frame_interval_seconds)
            jpeg_bytes, _ = self._processor.get_preview_frame_jpeg()
            if jpeg_bytes:
                frame_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
            video = VideoFrame.from_ndarray(frame, format="bgr24")
            pts, time_base = await self.next_timestamp()
            video.pts = pts
            video.time_base = time_base or Fraction(1, 90000)
            return video


class WebRTCService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        cfg = load_streaming_runtime_config().get("streaming", {})
        webrtc_cfg = cfg.get("webrtc", {})
        self._enabled = bool(cfg.get("enabled", True)) and bool(webrtc_cfg.get("enabled", False))
        self._max_clients_per_camera = int(webrtc_cfg.get("max_clients_per_camera", 5))
        self._target_latency_ms = int(webrtc_cfg.get("target_latency_ms", 500))
        self._stun_servers = list(webrtc_cfg.get("stun_servers") or [])
        self._sessions: dict[str, _PreviewSessionRecord] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_status(self, camera_id: str) -> dict:
        with self._lock:
            sessions = [record for record in self._sessions.values() if record.camera_id == camera_id]
        return {
            "camera_id": camera_id,
            "enabled": self._enabled,
            "available": AIORTC_AVAILABLE,
            "detail": None if AIORTC_AVAILABLE else AIORTC_IMPORT_ERROR,
            "active_sessions": len(sessions),
            "max_clients_per_camera": self._max_clients_per_camera,
            "sessions": [
                StreamPreviewSession(
                    camera_id=record.camera_id,
                    preview_type="webrtc",
                    session_id=record.session_id,
                    status=record.status,
                    client_count=1,
                    started_at=record.started_at,
                    last_seen_at=record.last_seen_at,
                    detail=record.detail,
                ).model_dump(mode="json")
                for record in sessions
            ],
            "fallback_url": f"/api/streams/{camera_id}/mjpeg",
        }

    async def handle_offer(self, camera_id: str, payload: WebRTCOfferRequest | dict) -> WebRTCAnswerResponse:
        offer = payload if isinstance(payload, WebRTCOfferRequest) else WebRTCOfferRequest.model_validate(payload)
        processor = get_stream_session_manager().get_stream_processor(camera_id)
        if processor is None:
            return WebRTCAnswerResponse(
                status="unavailable",
                detail="stream is not running",
                preview_url=f"/api/streams/{camera_id}/mjpeg",
            )
        if not self._enabled:
            return WebRTCAnswerResponse(
                status="disabled",
                detail="WebRTC preview is disabled by runtime configuration",
                preview_url=f"/api/streams/{camera_id}/mjpeg",
            )
        if not AIORTC_AVAILABLE:
            return WebRTCAnswerResponse(
                status="fallback",
                detail=AIORTC_IMPORT_ERROR or "aiortc is unavailable",
                preview_url=f"/api/streams/{camera_id}/mjpeg",
            )
        with self._lock:
            active = [record for record in self._sessions.values() if record.camera_id == camera_id]
            if len(active) >= self._max_clients_per_camera:
                return WebRTCAnswerResponse(
                    status="capacity",
                    detail="WebRTC client limit reached",
                    preview_url=f"/api/streams/{camera_id}/mjpeg",
                )

        frame_interval = max(1.0 / 15.0, self._target_latency_ms / 1000.0 / 4.0)
        configuration = RTCConfiguration(
            iceServers=[RTCIceServer(urls=self._stun_servers)] if self._stun_servers else []
        )
        pc = RTCPeerConnection(configuration=configuration)
        session_id = f"webrtc_{uuid.uuid4().hex[:12]}"
        record = _PreviewSessionRecord(
            camera_id=camera_id,
            session_id=session_id,
            started_at=_now_iso(),
            last_seen_at=_now_iso(),
            status="connecting",
            pc=pc,
            processor=processor,
        )
        try:
            pc.addTrack(LatestPreviewTrack(processor, frame_interval))  # type: ignore[operator]

            @pc.on("connectionstatechange")
            async def _on_state_change():
                record.last_seen_at = _now_iso()
                record.status = getattr(pc, "connectionState", "unknown")
                if record.status in {"failed", "closed", "disconnected"}:
                    await self._remove_session(session_id, close_peer=False)

            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            processor.increment_preview_clients(1)
            with self._lock:
                self._sessions[session_id] = record
            record.status = "connected"
            self._increment_metric("stream_webrtc_sessions_total")
            return WebRTCAnswerResponse(
                sdp=pc.localDescription.sdp,
                type=pc.localDescription.type,
                status="ok",
            )
        except Exception as exc:
            logger.warning("WebRTC offer handling failed for %s: %s", camera_id, exc)
            await self._safe_close(pc)
            return WebRTCAnswerResponse(
                status="fallback",
                detail=str(exc),
                preview_url=f"/api/streams/{camera_id}/mjpeg",
            )

    async def stop(self, camera_id: str) -> dict:
        with self._lock:
            session_ids = [record.session_id for record in self._sessions.values() if record.camera_id == camera_id]
        for session_id in session_ids:
            await self._remove_session(session_id)
        return {"camera_id": camera_id, "stopped_sessions": len(session_ids), "status": "ok"}

    async def _remove_session(self, session_id: str, *, close_peer: bool = True) -> None:
        with self._lock:
            record = self._sessions.pop(session_id, None)
        if record is None:
            return
        processor = record.processor
        if processor is not None:
            try:
                processor.increment_preview_clients(-1)
            except Exception:
                pass
        if close_peer and record.pc is not None:
            await self._safe_close(record.pc)

    async def _safe_close(self, pc) -> None:
        try:
            await pc.close()
        except Exception:
            pass

    def _increment_metric(self, name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics

            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics

            metrics.increment(name, count)
        except Exception:
            pass


_webrtc_service: WebRTCService | None = None


def get_webrtc_service() -> WebRTCService:
    global _webrtc_service
    if _webrtc_service is None:
        _webrtc_service = WebRTCService()
    return _webrtc_service
