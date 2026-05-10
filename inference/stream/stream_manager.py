from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from inference.monitoring.metrics import deregister_stream
from inference.stream.stream_session_manager import get_runtime_stream_session_manager

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Lifecycle manager for multiple concurrent StreamProcessor instances.

    Streams are identified by a caller-supplied or auto-generated stream_id.
    The manager is thread-safe: add_stream / remove_stream can be called
    concurrently from API handlers.

    ModelPool loading is triggered lazily on the first add_stream call so
    the manager can be constructed at module import time without requiring
    model files to be present.

    Usage:
        mgr = get_stream_manager()
        sid = mgr.add_stream("rtsp://cam1/stream")
        mgr.list_streams()
        mgr.remove_stream(sid)
    """

    def __init__(self) -> None:
        from inference.model_pool import get_model_pool
        self._pool = get_model_pool()
        self._streams: dict[str, object] = {}  # stream_id → StreamProcessor
        self._lock = threading.Lock()
        self._counter = 0

    # ── pool bootstrap ────────────────────────────────────────────────────────

    def _ensure_pool_loaded(self) -> None:
        """Load ModelPool once if not already loaded."""
        if self._pool.is_loaded:
            return
        from ml.runtime import ModelRouter, system_boot_check
        system_boot_check()
        router = ModelRouter()
        weapon = router.get_model("weapon")
        phone = router.get_model("phone")
        self._pool.load(
            weapon_path=weapon["resolved_path"],
            phone_path=phone["resolved_path"],
        )
        logger.info("StreamManager: ModelPool loaded via ModelRouter")

    # ── stream lifecycle ──────────────────────────────────────────────────────

    def add_stream(self, source: str, stream_id: str | None = None) -> str:
        """
        Create and start a new StreamProcessor.

        Returns the stream_id that was assigned (caller-supplied or auto-generated).
        Raises ValueError if stream_id already exists.
        """
        self._ensure_pool_loaded()

        with self._lock:
            if stream_id is None:
                stream_id = f"stream_{self._counter}"
                self._counter += 1

            if stream_id in self._streams:
                raise ValueError(f"StreamManager: stream '{stream_id}' already exists")

            from inference.stream.stream_processor import StreamProcessor
            proc = StreamProcessor(stream_id=stream_id, source=source, model_pool=self._pool)
            proc.start()
            self._streams[stream_id] = proc
            get_runtime_stream_session_manager().register(proc)

        logger.info(
            json.dumps({
                "event": "stream_added",
                "stream_id": stream_id,
                "source": source,
                "total_streams": len(self._streams),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )
        return stream_id

    def remove_stream(self, stream_id: str) -> bool:
        """
        Stop and remove a stream by stream_id.

        Returns True if found and removed, False if stream_id did not exist.
        """
        with self._lock:
            proc = self._streams.pop(stream_id, None)

        if proc is None:
            return False

        proc.stop()
        get_runtime_stream_session_manager().deregister(stream_id)
        deregister_stream(stream_id)

        logger.info(
            json.dumps({
                "event": "stream_removed",
                "stream_id": stream_id,
                "remaining_streams": len(self._streams),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )
        return True

    def remove_all_streams(self) -> None:
        """Stop all active streams (called on application shutdown)."""
        with self._lock:
            stream_ids = list(self._streams.keys())

        for sid in stream_ids:
            self.remove_stream(sid)

    # ── introspection ─────────────────────────────────────────────────────────

    def list_streams(self) -> list[dict]:
        """Return status snapshots for all registered streams."""
        with self._lock:
            procs = list(self._streams.values())
        return [p.get_status() for p in procs]

    def get_stream(self, stream_id: str) -> object | None:
        """Return the StreamProcessor for stream_id, or None."""
        with self._lock:
            return self._streams.get(stream_id)

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for p in self._streams.values() if p.is_running)

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._streams)

    def health_summary(self) -> dict:
        """Compact health snapshot for the /health endpoint."""
        from inference.monitoring.metrics import all_stream_snapshots
        runtime_summary = get_runtime_stream_session_manager().health_summary()
        return {
            "active_streams": self.active_count,
            "total_streams": self.total_count,
            "model_pool_loaded": self._pool.is_loaded,
            "stream_metrics": all_stream_snapshots(),
            "streaming": runtime_summary.get("streaming", {}),
            "stream_health": runtime_summary.get("streams", []),
        }


# Process-wide singleton
_manager: StreamManager | None = None
_manager_lock = threading.Lock()


def get_stream_manager() -> StreamManager:
    """Return the process-wide StreamManager singleton (lazy-init)."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = StreamManager()
    return _manager
