from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 30.0
_DEFAULT_QUEUE_SIZE = 10
_DEFAULT_MAX_CLIENTS = 32
_DEFAULT_MIN_INTERVAL = 0.5


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        cfg = load_runtime_config("forensic_console")
        return cfg.get("websocket_frames", {})
    except Exception:
        return {}


class _FrameClient:
    def __init__(self, websocket: WebSocket, queue_size: int) -> None:
        self.websocket = websocket
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._dropped = 0

    def enqueue(self, message: dict) -> None:
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._dropped += 1

    async def drain(self) -> dict | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class WebSocketFrameService:
    """
    Manages connected /ws/frames WebSocket clients and broadcasts frame-update
    messages.  Thread-safe for calls from the inference pipeline; async-safe
    for FastAPI WebSocket handlers.
    """

    def __init__(self) -> None:
        self._clients: dict[int, _FrameClient] = {}
        self._lock = threading.Lock()
        self._cfg: dict | None = None
        # last-broadcast tracking per camera to enforce min interval
        self._last_broadcast: dict[str, float] = {}

    def _get_cfg(self) -> dict:
        if self._cfg is None:
            self._cfg = _load_config()
        return self._cfg

    @property
    def _max_clients(self) -> int:
        return int(self._get_cfg().get("max_clients", _DEFAULT_MAX_CLIENTS))

    @property
    def _queue_size(self) -> int:
        return int(self._get_cfg().get("queue_size_per_client", _DEFAULT_QUEUE_SIZE))

    @property
    def _min_interval(self) -> float:
        return float(self._get_cfg().get("broadcast_min_interval_seconds", _DEFAULT_MIN_INTERVAL))

    @property
    def _heartbeat_interval(self) -> float:
        return float(self._get_cfg().get("heartbeat_interval_seconds", _HEARTBEAT_INTERVAL))

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast_frame_update(
        self,
        camera_id: str,
        frame_id: int | None,
        timestamp: float | None,
        image_url: str | None,
        annotated_image_url: str | None,
        mjpeg_url: str | None,
        overlay_count: int,
        stale: bool,
    ) -> None:
        """Called from sync inference pipeline threads."""
        now = time.time()
        last = self._last_broadcast.get(camera_id, 0.0)
        if now - last < self._min_interval:
            return
        self._last_broadcast[camera_id] = now

        message = {
            "type": "frame_update",
            "camera_id": camera_id,
            "frame_id": frame_id,
            "timestamp": timestamp,
            "image_url": image_url,
            "annotated_image_url": annotated_image_url,
            "mjpeg_url": mjpeg_url,
            "overlay_count": overlay_count,
            "stale": stale,
        }

        with self._lock:
            clients = list(self._clients.values())

        for client in clients:
            client.enqueue(message)

        # Update metrics
        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment("websocket_frame_messages")
        except Exception:
            pass

    async def handle_connection(self, websocket: WebSocket) -> None:
        """Async handler for /ws/frames connections."""
        with self._lock:
            if len(self._clients) >= self._max_clients:
                await websocket.close(code=1013, reason="capacity")
                return
            client_id = id(websocket)
            client = _FrameClient(websocket, self._queue_size)
            self._clients[client_id] = client

        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment("websocket_frame_clients")
        except Exception:
            pass

        logger.debug("ws/frames client connected id=%s total=%s", client_id, self.client_count())

        try:
            await websocket.accept()
            last_hb = time.monotonic()

            while True:
                # Send queued messages
                while True:
                    msg = await client.drain()
                    if msg is None:
                        break
                    try:
                        await websocket.send_json(msg)
                    except Exception:
                        return

                # Heartbeat
                now = time.monotonic()
                if now - last_hb >= self._heartbeat_interval:
                    try:
                        await websocket.send_json({"type": "heartbeat", "ts": time.time()})
                    except Exception:
                        return
                    last_hb = now

                await asyncio.sleep(0.1)

        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("ws/frames client error id=%s: %s", client_id, exc)
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
            logger.debug("ws/frames client disconnected id=%s", client_id)
            try:
                from inference.metrics import metrics as core_metrics
                with core_metrics._lock:
                    core_metrics.websocket_frame_clients = max(0, getattr(core_metrics, "websocket_frame_clients", 1) - 1)
            except Exception:
                pass


_ws_frame_service: WebSocketFrameService | None = None
_ws_frame_service_lock = threading.Lock()


def get_websocket_frame_service() -> WebSocketFrameService:
    global _ws_frame_service
    if _ws_frame_service is None:
        with _ws_frame_service_lock:
            if _ws_frame_service is None:
                _ws_frame_service = WebSocketFrameService()
    return _ws_frame_service
