from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.api.websocket_security import accepted_ws_subprotocol
from app.api.object_authorization import can_access_camera, can_access_identity
from app.models.security_models import AuditAction
from app.services.audit_log_service import get_audit_log_service

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 30.0
_DEFAULT_QUEUE_SIZE = 16
_DEFAULT_MAX_CLIENTS = 32
_DEFAULT_MIN_INTERVAL = 0.2


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        cfg = load_runtime_config("handoff_rules")
        return {}  # no specific WS sub-key yet
    except Exception:
        return {}


class _HandoffClient:
    def __init__(self, websocket: WebSocket, queue_size: int, user: Any = None) -> None:
        self.websocket = websocket
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._dropped = 0
        self.user = user

    def enqueue(self, message: dict) -> None:
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._dropped += 1
            try:
                from inference.metrics import metrics as core_metrics
                core_metrics.increment("websocket_handoff_dropped_messages")
            except Exception:
                pass

    async def drain(self) -> dict | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


class WebSocketHandoffService:
    """Broadcast cross-camera handoff updates to connected /ws/handoffs clients."""

    def __init__(self) -> None:
        self._clients: dict[int, _HandoffClient] = {}
        self._lock = threading.Lock()
        self._last_broadcast: dict[str, float] = {}

    @property
    def _max_clients(self) -> int:
        return _DEFAULT_MAX_CLIENTS

    @property
    def _queue_size(self) -> int:
        return _DEFAULT_QUEUE_SIZE

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast_handoff_update(self, handoff: dict) -> None:
        hid = handoff.get("handoff_id", "")
        now = time.time()
        if now - self._last_broadcast.get(hid, 0.0) < _DEFAULT_MIN_INTERVAL:
            return
        self._last_broadcast[hid] = now

        message = {
            "type": "handoff_update",
            "handoff_id": hid,
            "state": handoff.get("state", ""),
            "source_camera": handoff.get("source_camera", ""),
            "target_camera": handoff.get("target_camera", ""),
            "identity_id": handoff.get("identity_id"),
            "source_track_id": handoff.get("source_track_id"),
            "target_track_id": handoff.get("target_track_id"),
            "confidence": handoff.get("confidence", 0.0),
            "eta_seconds": handoff.get("eta_seconds"),
            "timestamp": now,
        }

        with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            if client.user is not None:
                source_camera = str(handoff.get("source_camera") or "")
                target_camera = str(handoff.get("target_camera") or "")
                identity_id = str(handoff.get("identity_id") or "")
                if not any(
                    (
                        source_camera and can_access_camera(client.user, source_camera),
                        target_camera and can_access_camera(client.user, target_camera),
                        identity_id and can_access_identity(client.user, identity_id),
                    )
                ):
                    continue
            client.enqueue(message)

        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment("websocket_handoff_messages")
        except Exception:
            pass

    async def handle_connection(self, websocket: WebSocket, user: Any = None) -> None:
        with self._lock:
            if len(self._clients) >= self._max_clients:
                get_audit_log_service().record(
                    AuditAction.WEBSOCKET_DENIED,
                    user=user,
                    resource_type="websocket",
                    resource_id="/ws/handoffs",
                    success=False,
                    detail="WebSocket capacity reached",
                    request=websocket,
                )
                await websocket.close(code=1013, reason="capacity")
                return
            client_id = id(websocket)
            client = _HandoffClient(websocket, self._queue_size, user=user)
            self._clients[client_id] = client

        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment("websocket_handoff_clients")
        except Exception:
            pass

        logger.debug("ws/handoffs client connected id=%s", client_id)

        try:
            await websocket.accept(subprotocol=accepted_ws_subprotocol(websocket))
            last_hb = time.monotonic()

            while True:
                while True:
                    msg = await client.drain()
                    if msg is None:
                        break
                    try:
                        await websocket.send_json(msg)
                    except Exception:
                        return

                now = time.monotonic()
                if now - last_hb >= _HEARTBEAT_INTERVAL:
                    try:
                        await websocket.send_json({"type": "heartbeat", "ts": time.time()})
                    except Exception:
                        return
                    last_hb = now

                await asyncio.sleep(0.1)

        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.debug("ws/handoffs client error id=%s: %s", client_id, exc)
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
            logger.debug("ws/handoffs client disconnected id=%s", client_id)
            get_audit_log_service().record(
                AuditAction.WEBSOCKET_DISCONNECTED,
                user=user,
                resource_type="websocket",
                resource_id="/ws/handoffs",
                request=websocket,
            )
            try:
                from inference.metrics import metrics as core_metrics
                with core_metrics._lock:
                    core_metrics.websocket_handoff_clients = max(
                        0, getattr(core_metrics, "websocket_handoff_clients", 1) - 1
                    )
            except Exception:
                pass


_ws_handoff_service: WebSocketHandoffService | None = None
_ws_handoff_service_lock = threading.Lock()


def get_websocket_handoff_service() -> WebSocketHandoffService:
    global _ws_handoff_service
    if _ws_handoff_service is None:
        with _ws_handoff_service_lock:
            if _ws_handoff_service is None:
                _ws_handoff_service = WebSocketHandoffService()
    return _ws_handoff_service
