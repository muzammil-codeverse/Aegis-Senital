from __future__ import annotations

import threading
from typing import Protocol

from app.services.rtsp_ingest_service import load_streaming_runtime_config


class StreamProcessorProtocol(Protocol):
    stream_id: str
    camera_id: str

    @property
    def is_running(self) -> bool: ...

    def get_status(self) -> dict: ...
    def get_stream_health(self) -> dict: ...
    def get_stream_stats(self) -> dict: ...
    def get_preview_frame_jpeg(self) -> tuple[bytes | None, str | None]: ...


class StreamRuntimeSessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_stream_id: dict[str, StreamProcessorProtocol] = {}
        self._by_camera_id: dict[str, StreamProcessorProtocol] = {}

    def register(self, processor: StreamProcessorProtocol) -> None:
        with self._lock:
            self._by_stream_id[processor.stream_id] = processor
            self._by_camera_id[processor.camera_id] = processor

    def deregister(self, stream_id: str) -> None:
        with self._lock:
            processor = self._by_stream_id.pop(stream_id, None)
            if processor is not None:
                self._by_camera_id.pop(processor.camera_id, None)

    def get_by_stream_id(self, stream_id: str) -> StreamProcessorProtocol | None:
        with self._lock:
            return self._by_stream_id.get(stream_id)

    def get_by_camera_id(self, camera_id: str) -> StreamProcessorProtocol | None:
        with self._lock:
            return self._by_camera_id.get(camera_id)

    def list_processors(self) -> list[StreamProcessorProtocol]:
        with self._lock:
            return list(self._by_stream_id.values())

    def list_statuses(self) -> list[dict]:
        return [processor.get_status() for processor in self.list_processors()]

    def health_summary(self) -> dict:
        cfg = load_streaming_runtime_config().get("streaming", {})
        enabled = bool(cfg.get("enabled", True))
        processors = self.list_processors()
        health_items = [processor.get_stream_health() for processor in processors]
        degraded = sum(1 for item in health_items if item.get("status") in {"degraded", "reconnecting"})
        failed = sum(1 for item in health_items if item.get("status") == "failed")
        if not enabled:
            status = "disabled"
        elif failed:
            status = "failed"
        elif degraded:
            status = "degraded"
        else:
            status = "healthy"
        last_error = next((item.get("last_error") for item in health_items if item.get("last_error")), None)
        return {
            "streaming": {
                "enabled": enabled,
                "status": status,
                "active_streams": sum(1 for processor in processors if processor.is_running),
                "degraded_streams": degraded,
                "failed_streams": failed,
                "webrtc_enabled": bool(cfg.get("webrtc", {}).get("enabled", False)),
                "hls_enabled": bool(cfg.get("hls", {}).get("enabled", False)),
                "last_error": last_error,
            },
            "streams": health_items,
        }


_runtime_session_manager: StreamRuntimeSessionManager | None = None
_runtime_session_manager_lock = threading.Lock()


def get_runtime_stream_session_manager() -> StreamRuntimeSessionManager:
    global _runtime_session_manager
    if _runtime_session_manager is None:
        with _runtime_session_manager_lock:
            if _runtime_session_manager is None:
                _runtime_session_manager = StreamRuntimeSessionManager()
    return _runtime_session_manager
