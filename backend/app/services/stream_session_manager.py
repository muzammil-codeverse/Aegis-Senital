from __future__ import annotations

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class StreamSessionState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


class _SessionEntry:
    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self.state = StreamSessionState.STOPPED
        self.started_at: float | None = None
        self.stopped_at: float | None = None
        self.error_reason: str | None = None
        self.stream_id: str | None = None
        self.updated_at: float = time.time()

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "state": self.state.value,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "error_reason": self.error_reason,
            "stream_id": self.stream_id,
            "updated_at": self.updated_at,
        }


class StreamSessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionEntry] = {}

    def _get_or_create(self, camera_id: str) -> _SessionEntry:
        with self._lock:
            if camera_id not in self._sessions:
                self._sessions[camera_id] = _SessionEntry(camera_id)
            return self._sessions[camera_id]

    def _get_camera_source(self, camera_id: str) -> str | None:
        try:
            from app.services.camera_registry import get_camera_registry
            camera = get_camera_registry().get_camera(camera_id)
            return camera.source_uri if camera else None
        except Exception:
            return None

    def _update_camera_status(self, camera_id: str, status: str, reason: str | None = None) -> None:
        try:
            from app.services.camera_registry import get_camera_registry
            get_camera_registry().set_camera_status(camera_id, status, reason=reason)
        except Exception:
            pass

    def _emit_event(self, event_type: str, camera_id: str, data: dict | None = None) -> None:
        try:
            from core.event_bus import EventType, get_event_bus
            payload = {"camera_id": camera_id, "event": event_type, **(data or {})}
            get_event_bus().publish(EventType.SYSTEM_EVENT, payload, source=camera_id, priority=5)
        except Exception:
            pass

    def start_stream(self, camera_id: str) -> dict:
        session = self._get_or_create(camera_id)
        with self._lock:
            if session.state == StreamSessionState.RUNNING:
                return {**session.to_dict(), "detail": "already running"}
            if session.state == StreamSessionState.STARTING:
                return {**session.to_dict(), "detail": "already starting"}
            session.state = StreamSessionState.STARTING
            session.error_reason = None
            session.updated_at = time.time()

        source_uri = self._get_camera_source(camera_id)
        try:
            if not source_uri:
                raise RuntimeError(f"Camera '{camera_id}' has no source_uri configured")
            from inference.stream.stream_manager import get_stream_manager
            mgr = get_stream_manager()
            stream_id = f"cam_{camera_id}"
            if session.stream_id:
                try:
                    mgr.remove_stream(session.stream_id)
                except Exception:
                    pass
            assigned_id = mgr.add_stream(source=source_uri, stream_id=stream_id)
            with self._lock:
                session.state = StreamSessionState.RUNNING
                session.stream_id = assigned_id
                session.started_at = time.time()
                session.stopped_at = None
                session.error_reason = None
                session.updated_at = time.time()
            self._update_camera_status(camera_id, "online")
            self._emit_event("stream_started", camera_id, {"stream_id": assigned_id})
            logger.info("Stream started for camera %s (stream_id=%s)", camera_id, assigned_id)
        except Exception as exc:
            err_msg = str(exc)
            with self._lock:
                session.state = StreamSessionState.ERROR
                session.error_reason = err_msg
                session.updated_at = time.time()
            self._update_camera_status(camera_id, "error", reason=err_msg)
            self._emit_event("stream_error", camera_id, {"error": err_msg})
            logger.warning("Stream start failed for camera %s: %s", camera_id, err_msg)
            # Increment failure metric safely
            try:
                from inference.monitoring.metrics import get_metrics
                get_metrics().increment("stream_start_failures")
            except Exception:
                pass

        return session.to_dict()

    def stop_stream(self, camera_id: str) -> dict:
        session = self._get_or_create(camera_id)
        with self._lock:
            if session.state == StreamSessionState.STOPPED:
                return {**session.to_dict(), "detail": "already stopped"}
            session.state = StreamSessionState.STOPPING
            stream_id = session.stream_id
            session.updated_at = time.time()

        if stream_id:
            try:
                from inference.stream.stream_manager import get_stream_manager
                get_stream_manager().remove_stream(stream_id)
            except Exception as exc:
                logger.warning("Stream remove failed for %s: %s", camera_id, exc)

        with self._lock:
            session.state = StreamSessionState.STOPPED
            session.stopped_at = time.time()
            session.stream_id = None
            session.updated_at = time.time()

        self._update_camera_status(camera_id, "offline")
        self._emit_event("stream_stopped", camera_id)
        return session.to_dict()

    def pause_stream(self, camera_id: str) -> dict:
        session = self._get_or_create(camera_id)
        with self._lock:
            if session.state != StreamSessionState.RUNNING:
                return {**session.to_dict(), "detail": f"cannot pause from state {session.state.value}"}
            session.state = StreamSessionState.PAUSED
            session.updated_at = time.time()
        self._update_camera_status(camera_id, "degraded", reason="paused by operator")
        self._emit_event("stream_paused", camera_id)
        return session.to_dict()

    def resume_stream(self, camera_id: str) -> dict:
        session = self._get_or_create(camera_id)
        with self._lock:
            if session.state != StreamSessionState.PAUSED:
                return {**session.to_dict(), "detail": f"cannot resume from state {session.state.value}"}
            session.state = StreamSessionState.RUNNING
            session.updated_at = time.time()
        self._update_camera_status(camera_id, "online")
        self._emit_event("stream_resumed", camera_id)
        return session.to_dict()

    def restart_stream(self, camera_id: str) -> dict:
        self.stop_stream(camera_id)
        return self.start_stream(camera_id)

    def get_stream_state(self, camera_id: str) -> dict:
        return self._get_or_create(camera_id).to_dict()

    def list_stream_states(self) -> list[dict]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.to_dict() for s in sessions]


_session_manager: StreamSessionManager | None = None
_session_manager_lock = threading.Lock()


def get_stream_session_manager() -> StreamSessionManager:
    global _session_manager
    if _session_manager is None:
        with _session_manager_lock:
            if _session_manager is None:
                _session_manager = StreamSessionManager()
    return _session_manager
