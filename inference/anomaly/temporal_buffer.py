from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone

from inference.anomaly.schemas import AnomalyWindow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CameraWindow:
    """Mutable rolling window for a single camera."""

    def __init__(self, camera_id: str, window_seconds: float, sample_rate: int) -> None:
        self.camera_id = camera_id
        self.window_seconds = window_seconds
        self.sample_rate = sample_rate
        self._frames: deque[dict] = deque()
        self._detections: deque[dict] = deque()
        self._tracks: deque[dict] = deque()
        self._last_segmentation: dict | None = None
        self._window_start_ts: str = _now_iso()
        self._frame_counter: int = 0

    def add_frame(
        self,
        frame_id: int,
        timestamp: float,
        detections: list[dict],
        tracks: list[dict],
        segmentation: dict | None = None,
    ) -> None:
        self._frame_counter += 1
        # Sample every N-th frame to avoid storing raw pixels
        if self._frame_counter % self.sample_rate != 0:
            return
        cutoff = time.time() - self.window_seconds
        frame_ref = {"frame_id": frame_id, "timestamp": timestamp}
        self._frames.append(frame_ref)
        for det in detections:
            det_copy = dict(det)
            det_copy["_ts"] = timestamp
            self._detections.append(det_copy)
        for trk in tracks:
            trk_copy = dict(trk)
            trk_copy["_ts"] = timestamp
            self._tracks.append(trk_copy)
        if segmentation is not None:
            self._last_segmentation = segmentation
        self._evict(cutoff)

    def _evict(self, cutoff: float) -> None:
        while self._frames and self._frames[0].get("timestamp", 0) < cutoff:
            self._frames.popleft()
        while self._detections and self._detections[0].get("_ts", 0) < cutoff:
            self._detections.popleft()
        while self._tracks and self._tracks[0].get("_ts", 0) < cutoff:
            self._tracks.popleft()

    def snapshot(self) -> AnomalyWindow:
        now_iso = _now_iso()
        return AnomalyWindow(
            camera_id=self.camera_id,
            start_ts=self._window_start_ts,
            end_ts=now_iso,
            frames=list(self._frames),
            detections=list(self._detections),
            tracks=list(self._tracks),
            segmentation=self._last_segmentation,
        )

    def clear(self) -> None:
        self._frames.clear()
        self._detections.clear()
        self._tracks.clear()
        self._last_segmentation = None
        self._window_start_ts = _now_iso()
        self._frame_counter = 0


class TemporalBuffer:
    """
    Thread-safe rolling temporal buffer for all active cameras.

    Stores lightweight frame metadata (not raw pixels) per camera within a
    configurable rolling time window, then provides AnomalyWindow snapshots
    for downstream rule engine and model adapters.
    """

    def __init__(self, window_seconds: float = 5.0, sample_rate: int = 5) -> None:
        self._window_seconds = window_seconds
        self._sample_rate = max(1, sample_rate)
        self._cameras: dict[str, CameraWindow] = {}
        self._lock = threading.RLock()

    def add_frame(
        self,
        camera_id: str,
        frame_id: int,
        timestamp: float,
        detections: list[dict],
        tracks: list[dict],
        segmentation: dict | None = None,
    ) -> None:
        with self._lock:
            if camera_id not in self._cameras:
                self._cameras[camera_id] = CameraWindow(
                    camera_id, self._window_seconds, self._sample_rate
                )
            self._cameras[camera_id].add_frame(
                frame_id, timestamp, detections, tracks, segmentation
            )

    def get_window(self, camera_id: str) -> AnomalyWindow | None:
        with self._lock:
            cam = self._cameras.get(camera_id)
            if cam is None:
                return None
            return cam.snapshot()

    def clear_camera(self, camera_id: str) -> None:
        with self._lock:
            cam = self._cameras.get(camera_id)
            if cam is not None:
                cam.clear()

    def active_cameras(self) -> list[str]:
        with self._lock:
            return list(self._cameras.keys())

    def buffer_sizes(self) -> dict[str, int]:
        with self._lock:
            return {cid: len(c._frames) for cid, c in self._cameras.items()}
