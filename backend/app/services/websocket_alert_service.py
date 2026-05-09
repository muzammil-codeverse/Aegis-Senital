from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from core.event_bus import EventType, EventRecord, get_event_bus
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class _Client:
    websocket: WebSocket
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


class WebSocketAlertService:
    def __init__(self) -> None:
        cfg = _safe_alert_rules().get("websocket", {})
        self._heartbeat_seconds = float(cfg.get("heartbeat_seconds", 30.0))
        self._queue_size = int(cfg.get("outbound_queue_size", 100))
        self._max_clients = int(cfg.get("max_clients", 100))
        self._clients: set[_Client] = set()
        self._lock = threading.RLock()
        get_event_bus().subscribe(EventType.ALERT_EVENT, self._on_alert_event)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        client = _Client(
            websocket=websocket,
            queue=asyncio.Queue(maxsize=self._queue_size),
            loop=asyncio.get_running_loop(),
        )
        with self._lock:
            if len(self._clients) >= self._max_clients:
                reject = True
            else:
                reject = False
                self._clients.add(client)
                _set_core_metric("websocket_clients", len(self._clients))
        if reject:
            _increment_core_metric("websocket_dropped_messages")
            logger.warning("Rejecting alert websocket client: max client count reached")
            await websocket.close(code=1013)
            return
        try:
            await self._send_loop(client)
        except WebSocketDisconnect:
            logger.info("WebSocket alert client disconnected")
        finally:
            with self._lock:
                self._clients.discard(client)
                _set_core_metric("websocket_clients", len(self._clients))

    def _on_alert_event(self, record: EventRecord) -> None:
        payload = record.to_dict()
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.loop.call_soon_threadsafe(self._offer, client, payload)

    def _offer(self, client: _Client, payload: dict) -> None:
        if client.queue.full():
            _increment_core_metric("websocket_dropped_messages")
            return
        client.queue.put_nowait(payload)

    async def _send_loop(self, client: _Client) -> None:
        next_heartbeat = time.monotonic() + self._heartbeat_seconds
        while True:
            timeout = max(0.0, next_heartbeat - time.monotonic())
            try:
                payload = await asyncio.wait_for(client.queue.get(), timeout=timeout)
                await client.websocket.send_json(payload)
            except asyncio.TimeoutError:
                await client.websocket.send_json({"type": "heartbeat", "timestamp": time.time()})
                next_heartbeat = time.monotonic() + self._heartbeat_seconds


def _safe_alert_rules() -> dict:
    try:
        return load_runtime_config("alert_rules")
    except FileNotFoundError as exc:
        logger.warning("Alert rules config unavailable for websocket alert service: %s", exc)
        return {}


def _increment_core_metric(name: str) -> None:
    try:
        from inference.metrics import metrics
        metrics.increment(name)
    except Exception as exc:
        logger.warning("WebSocket metric increment failed for %s: %s", name, exc)


def _set_core_metric(name: str, value: int) -> None:
    try:
        from inference.metrics import metrics
        metrics.set_value(name, value)
    except Exception as exc:
        logger.warning("WebSocket metric update failed for %s: %s", name, exc)


websocket_alert_service = WebSocketAlertService()
