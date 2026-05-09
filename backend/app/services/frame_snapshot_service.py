from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

_MAX_SNAPSHOTS = 256
_SNAPSHOT_TTL = 600.0


class FrameSnapshotService:
    def __init__(
        self,
        max_snapshots: int = _MAX_SNAPSHOTS,
        ttl_seconds: float = _SNAPSHOT_TTL,
    ) -> None:
        self._lock = threading.RLock()
        self._frames: OrderedDict[str, dict] = OrderedDict()
        self._max = max_snapshots
        self._ttl = ttl_seconds

    def update_latest_frame(
        self,
        camera_id: str,
        frame_path: str | None = None,
        frame_id: int | None = None,
        timestamp: float | None = None,
        detections: list | None = None,
        overlays: list | None = None,
    ) -> None:
        ts = timestamp or time.time()
        with self._lock:
            self._evict_expired(ts)
            if len(self._frames) >= self._max and camera_id not in self._frames:
                self._frames.popitem(last=False)
            self._frames[camera_id] = {
                "camera_id": camera_id,
                "frame_path": frame_path,
                "frame_id": frame_id,
                "timestamp": ts,
                "detections": detections or [],
                "overlays": overlays or [],
                "updated_at": ts,
            }
            self._frames.move_to_end(camera_id)
        # Update camera registry frame timestamp
        try:
            from app.services.camera_registry import get_camera_registry
            get_camera_registry().mark_frame_seen(camera_id, timestamp=ts)
        except Exception:
            pass
        # Update metrics
        try:
            from inference.monitoring.metrics import get_metrics
            get_metrics().increment("latest_frame_updates")
        except Exception:
            pass

    def get_latest_frame(self, camera_id: str) -> dict:
        with self._lock:
            frame = self._frames.get(camera_id)
        if frame is None:
            return {
                "camera_id": camera_id,
                "frame_path": None,
                "frame_id": None,
                "timestamp": None,
                "detections": [],
                "overlays": [],
                "updated_at": None,
                "status": "no_frame",
            }
        return {**frame, "status": "ok"}

    def list_latest_frames(self) -> list[dict]:
        now = time.time()
        with self._lock:
            frames = [
                {**f, "status": "ok"}
                for f in self._frames.values()
                if now - float(f.get("timestamp") or 0) <= self._ttl
            ]
        return frames

    def _evict_expired(self, now: float) -> None:
        expired = [
            cid for cid, f in self._frames.items()
            if now - float(f.get("timestamp") or 0) > self._ttl
        ]
        for cid in expired:
            del self._frames[cid]


_snapshot_service: FrameSnapshotService | None = None
_snapshot_service_lock = threading.Lock()


def get_frame_snapshot_service() -> FrameSnapshotService:
    global _snapshot_service
    if _snapshot_service is None:
        with _snapshot_service_lock:
            if _snapshot_service is None:
                _snapshot_service = FrameSnapshotService()
    return _snapshot_service
