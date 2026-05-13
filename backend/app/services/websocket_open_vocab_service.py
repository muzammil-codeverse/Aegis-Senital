from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.api.object_authorization import can_access_camera, can_access_event_payload, can_access_incident
from core.event_bus import EventType, EventRecord, get_event_bus
from app.models.security_models import AuditAction
from app.services.audit_log_service import get_audit_log_service
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)

# Phase 25 — per-camera rate limiting defaults
_DEFAULT_MAX_EVENTS_PER_CAMERA_PER_SECOND: float = 2.0
_DEFAULT_MAX_DETECTIONS_PER_EVENT: int = 25
_DEFAULT_MAX_CLIENTS: int = 100
_DEFAULT_QUEUE_SIZE: int = 200
_DEFAULT_HEARTBEAT_SECONDS: float = 30.0


@dataclass(eq=False)
class _Client:
    websocket: WebSocket
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    user: Any = None


class WebSocketOpenVocabService:
    """
    Real-time WebSocket push for Open-Vocab scan results.

    Subscribes to OPEN_VOCAB_SCAN_RESULT events from the distributed event bus
    and fans out to all connected WebSocket clients.

    Rate limiting: max N events/camera/second. Extra events are dropped and
    counted in the rate_limited metric.
    Payload guard: detections array is capped at max_detections_per_event.
    """

    def __init__(self) -> None:
        cfg = _safe_streaming_config()
        self._heartbeat_seconds = float(cfg.get("heartbeat_seconds", _DEFAULT_HEARTBEAT_SECONDS))
        self._queue_size = int(cfg.get("outbound_queue_size", _DEFAULT_QUEUE_SIZE))
        self._max_clients = int(cfg.get("max_clients", _DEFAULT_MAX_CLIENTS))
        self._max_events_per_camera_per_second = float(
            cfg.get("max_events_per_camera_per_second", _DEFAULT_MAX_EVENTS_PER_CAMERA_PER_SECOND)
        )
        self._max_detections_per_event = int(
            cfg.get("max_detections_per_event", _DEFAULT_MAX_DETECTIONS_PER_EVENT)
        )
        self._publish_empty_results = bool(cfg.get("publish_empty_results", False))

        self._clients: set[_Client] = set()
        self._lock = threading.RLock()

        # Per-camera rate-limiting: camera_id → list of timestamps in last 1 second
        self._camera_event_times: dict[str, list[float]] = defaultdict(list)
        self._rate_lock = threading.Lock()

        # Phase 25 streaming metrics (counters, not Prometheus — exposed via snapshot())
        self._published_total: int = 0
        self._dropped_total: int = 0
        self._rate_limited_total: int = 0
        self._payload_bytes_total: int = 0
        self._last_push_timestamp: float | None = None
        self._scan_publish_latencies: list[float] = []  # capped at 100

        get_event_bus().subscribe(EventType.OPEN_VOCAB_SCAN_RESULT, self._on_scan_result)
        logger.info("WebSocketOpenVocabService initialized and subscribed to OPEN_VOCAB_SCAN_RESULT")

    # ── connection lifecycle ───────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, user: Any = None) -> None:
        await websocket.accept()
        client = _Client(
            websocket=websocket,
            queue=asyncio.Queue(maxsize=self._queue_size),
            loop=asyncio.get_running_loop(),
            user=user,
        )
        with self._lock:
            if len(self._clients) >= self._max_clients:
                reject = True
            else:
                reject = False
                self._clients.add(client)
                _set_metric("open_vocab_active_stream_subscribers", len(self._clients))

        if reject:
            _increment_metric("open_vocab_ws_events_dropped_total")
            with self._lock:
                self._dropped_total += 1
            logger.warning("Rejecting open-vocab websocket client: max client count reached")
            get_audit_log_service().record(
                AuditAction.WEBSOCKET_DENIED,
                user=user,
                resource_type="websocket",
                resource_id="/ws/open-vocab",
                success=False,
                detail="WebSocket capacity reached",
                request=websocket,
            )
            await websocket.close(code=1013)
            return

        try:
            await self._send_loop(client)
        except BaseException:
            logger.info("Open-vocab WebSocket client disconnected")
        finally:
            with self._lock:
                self._clients.discard(client)
                _set_metric("open_vocab_active_stream_subscribers", len(self._clients))
            get_audit_log_service().record(
                AuditAction.WEBSOCKET_DISCONNECTED,
                user=user,
                resource_type="websocket",
                resource_id="/ws/open-vocab",
                request=websocket,
            )

    # ── event handler (called from event bus subscriber thread) ───────────────

    def _on_scan_result(self, record: EventRecord) -> None:
        payload = record.to_dict().get("payload", {})
        if not isinstance(payload, dict):
            return

        camera_id = payload.get("camera_id") or record.source or "unknown"
        scan_ts = payload.get("summary", {}).get("scan_timestamp") or record.timestamp

        # Skip empty results if not configured to publish them
        detection_count = payload.get("summary", {}).get("detection_count", 0)
        if not self._publish_empty_results and detection_count == 0:
            return

        # Per-camera rate limiting
        if self._is_rate_limited(camera_id):
            _increment_metric("open_vocab_ws_event_rate_limited_total")
            with self._lock:
                self._rate_limited_total += 1
            return

        # Payload size guard: cap detections array
        ws_payload = dict(payload)
        detections = ws_payload.get("detections", [])
        if len(detections) > self._max_detections_per_event:
            ws_payload = dict(ws_payload)
            ws_payload["detections"] = detections[: self._max_detections_per_event]
            ws_payload["_detections_truncated"] = True

        # Do not include raw frames or embeddings
        ws_payload.pop("frame_data", None)
        ws_payload.pop("embedding", None)
        ws_payload.pop("embeddings", None)

        import json
        try:
            payload_bytes = len(json.dumps(ws_payload).encode())
        except Exception:
            payload_bytes = 0

        with self._lock:
            clients = list(self._clients)
            self._published_total += 1
            self._payload_bytes_total += payload_bytes
            self._last_push_timestamp = time.time()
            if scan_ts and isinstance(scan_ts, (int, float)):
                latency_ms = (time.time() - scan_ts) * 1000
                self._scan_publish_latencies.append(latency_ms)
                if len(self._scan_publish_latencies) > 100:
                    self._scan_publish_latencies.pop(0)

        _increment_metric("open_vocab_ws_events_published_total")
        _add_to_metric("open_vocab_ws_event_payload_bytes", payload_bytes)

        for client in clients:
            if client.user is not None:
                if not (
                    can_access_event_payload(client.user, ws_payload)
                    or can_access_camera(client.user, str(ws_payload.get("camera_id") or ""))
                    or can_access_incident(client.user, str(ws_payload.get("incident_id") or ""))
                ):
                    continue
            client.loop.call_soon_threadsafe(self._offer, client, ws_payload)

    def _is_rate_limited(self, camera_id: str) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            times = self._camera_event_times[camera_id]
            cutoff = now - 1.0
            times[:] = [t for t in times if t >= cutoff]
            if len(times) >= self._max_events_per_camera_per_second:
                return True
            times.append(now)
            return False

    def _offer(self, client: _Client, payload: dict) -> None:
        if client.queue.full():
            _increment_metric("open_vocab_ws_events_dropped_total")
            with self._lock:
                self._dropped_total += 1
            return
        client.queue.put_nowait(payload)

    # ── send loop ─────────────────────────────────────────────────────────────

    async def _send_loop(self, client: _Client) -> None:
        next_heartbeat = time.monotonic() + self._heartbeat_seconds
        while True:
            timeout = max(0.0, next_heartbeat - time.monotonic())
            try:
                payload = await asyncio.wait_for(client.queue.get(), timeout=timeout)
                await client.websocket.send_json({"type": "open_vocab_scan_result", "data": payload})
            except asyncio.TimeoutError:
                await client.websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                    "topic": "open_vocab",
                })
                next_heartbeat = time.monotonic() + self._heartbeat_seconds

    # ── introspection ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            avg_latency = (
                sum(self._scan_publish_latencies) / len(self._scan_publish_latencies)
                if self._scan_publish_latencies else 0.0
            )
            return {
                "active_subscribers": len(self._clients),
                "published_total": self._published_total,
                "dropped_total": self._dropped_total,
                "rate_limited_total": self._rate_limited_total,
                "payload_bytes_total": self._payload_bytes_total,
                "last_push_timestamp": self._last_push_timestamp,
                "scan_to_push_latency_ms_avg": round(avg_latency, 2),
            }


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_streaming_config() -> dict:
    try:
        cfg = load_runtime_config("open_vocab")
        return cfg.get("open_vocab_streaming", {})
    except FileNotFoundError as exc:
        logger.warning("Open-vocab streaming config unavailable: %s", exc)
        return {}


def _increment_metric(name: str, n: int = 1) -> None:
    try:
        from inference.monitoring.metrics import get_metrics
        get_metrics().increment(name)
    except Exception:
        pass


def _add_to_metric(name: str, value: int) -> None:
    try:
        from inference.monitoring.metrics import get_metrics
        m = get_metrics()
        current = getattr(m, name, 0)
        setattr(m, name, current + value)
    except Exception:
        pass


def _set_metric(name: str, value: int) -> None:
    try:
        from inference.monitoring.metrics import get_metrics
        m = get_metrics()
        setattr(m, name, value)
    except Exception:
        pass


# ── singleton ─────────────────────────────────────────────────────────────────

_service: WebSocketOpenVocabService | None = None
_service_lock = threading.Lock()


def get_websocket_open_vocab_service() -> WebSocketOpenVocabService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = WebSocketOpenVocabService()
    return _service
