from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)

_VIDEO_FILE_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v")
_DEFAULT_STREAMING_CONFIG: dict[str, Any] = {
    "streaming": {
        "ingest": {
            "reconnect": {
                "enabled": True,
                "max_attempts": 10,
                "initial_backoff_seconds": 1,
                "max_backoff_seconds": 30,
                "jitter": True,
            },
            "read_timeout_seconds": 10,
            "stale_frame_timeout_seconds": 5,
        },
        "processing": {
            "max_decode_fps": 30,
            "timestamp_source": "camera_or_system",
            "max_clock_skew_ms": 500,
        },
        "health": {
            "unhealthy_no_frame_seconds": 10,
            "degraded_latency_ms": 500,
            "failed_reconnect_threshold": 10,
        },
    }
}


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_streaming_runtime_config() -> dict[str, Any]:
    try:
        payload = load_runtime_config("streaming")
    except Exception:
        payload = {}
    return _merge_dict(_DEFAULT_STREAMING_CONFIG, payload)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_source_type(source: Any) -> str:
    if isinstance(source, int):
        return "webcam"
    text = str(source or "").strip().lower()
    if text.startswith("cosys_airsim://"):
        return "drone_simulation"
    if text.startswith("rtsp://"):
        return "rtsp"
    if text.endswith(_VIDEO_FILE_SUFFIXES):
        return "file"
    if text.isdigit():
        return "webcam"
    return "rtsp"


@dataclass(slots=True)
class DecodedFramePacket:
    camera_id: str
    frame: np.ndarray = field(repr=False)
    frame_index: int
    timestamp: str
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_timestamp: str | None = None
    width: int = 0
    height: int = 0
    fps_estimate: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "source_timestamp": self.source_timestamp,
            "frame_index": self.frame_index,
            "width": self.width,
            "height": self.height,
            "fps_estimate": self.fps_estimate,
            "metadata": dict(self.metadata),
        }


class RTSPIngestService:
    def __init__(
        self,
        camera_id: str,
        source: Any,
        source_type: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = _merge_dict(load_streaming_runtime_config(), config or {})
        streaming_cfg = cfg.get("streaming", {})
        ingest_cfg = streaming_cfg.get("ingest", {})
        processing_cfg = streaming_cfg.get("processing", {})
        health_cfg = streaming_cfg.get("health", {})
        reconnect_cfg = ingest_cfg.get("reconnect", {})

        self.camera_id = camera_id
        self.source = source
        self.source_type = str(source_type or _infer_source_type(source)).lower()
        self._config = cfg
        self._read_timeout_seconds = float(ingest_cfg.get("read_timeout_seconds", 10))
        self._stale_frame_timeout_seconds = float(ingest_cfg.get("stale_frame_timeout_seconds", 5))
        self._target_decode_fps = float(processing_cfg.get("max_decode_fps", 30))
        self._timestamp_source = str(processing_cfg.get("timestamp_source", "camera_or_system")).lower()
        self._max_clock_skew_ms = int(processing_cfg.get("max_clock_skew_ms", 500))
        self._unhealthy_no_frame_seconds = float(health_cfg.get("unhealthy_no_frame_seconds", 10))
        self._degraded_latency_ms = float(health_cfg.get("degraded_latency_ms", 500))
        self._failed_reconnect_threshold = int(health_cfg.get("failed_reconnect_threshold", 10))
        self._reconnect_enabled = bool(reconnect_cfg.get("enabled", True))
        self._reconnect_max_attempts = int(reconnect_cfg.get("max_attempts", 10))
        self._reconnect_initial_backoff_seconds = float(reconnect_cfg.get("initial_backoff_seconds", 1))
        self._reconnect_max_backoff_seconds = float(reconnect_cfg.get("max_backoff_seconds", 30))
        self._reconnect_jitter = bool(reconnect_cfg.get("jitter", True))

        self._capture: cv2.VideoCapture | None = None
        self._frame_index = 0
        self._frames_decoded_total = 0
        self._reconnect_attempts = 0
        self._offline_transitions = 0
        self._online_transitions = 0
        self._last_frame_at: str | None = None
        self._last_source_timestamp: str | None = None
        self._last_frame_monotonic: float | None = None
        self._last_error: str | None = None
        self._status = "stopped"
        self._fps_times: deque[float] = deque(maxlen=90)
        self._read_latency_ms: deque[float] = deque(maxlen=90)
        self._preview_lock = threading.RLock()
        self._latest_preview_jpeg: bytes | None = None
        self._latest_preview_at: str | None = None
        self._file_source_started_at = datetime.now(timezone.utc) if self.source_type == "file" else None

    def open(self) -> bool:
        if self._capture is not None and self._capture.isOpened():
            return True

        capture = cv2.VideoCapture(self._capture_source())
        for prop_name, value in (
            ("CAP_PROP_OPEN_TIMEOUT_MSEC", int(self._read_timeout_seconds * 1000)),
            ("CAP_PROP_READ_TIMEOUT_MSEC", int(self._read_timeout_seconds * 1000)),
            ("CAP_PROP_BUFFERSIZE", 1),
        ):
            if hasattr(cv2, prop_name):
                try:
                    capture.set(getattr(cv2, prop_name), value)
                except Exception:
                    pass

        if not capture.isOpened():
            self._capture = None
            self._mark_state("reconnecting", f"unable to open source '{self.source}'")
            return False

        self._capture = capture
        if self._status in {"reconnecting", "failed", "stopped"}:
            self._online_transitions += 1
        self._status = "healthy"
        self._last_error = None
        return True

    def read_packet(self, stop_event: threading.Event) -> DecodedFramePacket | None:
        while not stop_event.is_set():
            if not self.open():
                if not self._wait_for_reconnect(stop_event):
                    return None
                continue

            if self._last_frame_monotonic is not None:
                age = time.monotonic() - self._last_frame_monotonic
                if age >= self._stale_frame_timeout_seconds and self.source_type != "file":
                    self._mark_state("reconnecting", f"stale frame timeout after {age:.1f}s")
                    if not self._wait_for_reconnect(stop_event):
                        return None
                    continue

            read_started = time.monotonic()
            try:
                ret, frame = self._capture.read()  # type: ignore[union-attr]
            except Exception as exc:
                self._mark_state("reconnecting", f"capture read failed: {exc}")
                if not self._wait_for_reconnect(stop_event):
                    return None
                continue

            read_latency_ms = (time.monotonic() - read_started) * 1000.0
            self._read_latency_ms.append(read_latency_ms)
            if not ret or frame is None:
                if self.source_type == "file":
                    self._mark_state("stopped", "end of file")
                    return None
                self._mark_state("reconnecting", "frame read failed")
                if not self._wait_for_reconnect(stop_event):
                    return None
                continue

            if self._target_decode_fps > 0 and self._fps_times:
                interval = 1.0 / self._target_decode_fps
                delta = time.monotonic() - self._fps_times[-1]
                if delta < interval:
                    time.sleep(max(0.0, interval - delta))

            self._frames_decoded_total += 1
            self._fps_times.append(time.monotonic())
            self._last_frame_monotonic = time.monotonic()
            self._last_frame_at = _now_iso()
            self._last_source_timestamp = self._source_timestamp()
            self._last_error = None
            self._status = "healthy" if read_latency_ms <= self._degraded_latency_ms else "degraded"
            height, width = frame.shape[:2]
            packet = DecodedFramePacket(
                camera_id=self.camera_id,
                frame=frame,
                frame_index=self._frame_index,
                timestamp=self._normalized_timestamp(),
                source_timestamp=self._last_source_timestamp,
                width=width,
                height=height,
                fps_estimate=self.fps_decode,
                metadata={
                    "read_latency_ms": round(read_latency_ms, 2),
                    "source_type": self.source_type,
                },
            )
            self._frame_index += 1
            self._update_preview(frame)
            return packet

        return None

    def close(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None
        self._status = "stopped"

    @property
    def fps_decode(self) -> float:
        if len(self._fps_times) < 2:
            return 0.0
        elapsed = self._fps_times[-1] - self._fps_times[0]
        return round(len(self._fps_times) / elapsed, 2) if elapsed > 0 else 0.0

    @property
    def average_read_latency_ms(self) -> float:
        if not self._read_latency_ms:
            return 0.0
        return round(sum(self._read_latency_ms) / len(self._read_latency_ms), 2)

    def get_latest_preview_jpeg(self) -> tuple[bytes | None, str | None]:
        with self._preview_lock:
            return self._latest_preview_jpeg, self._latest_preview_at

    def snapshot(self) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        age_seconds = (
            round(now_monotonic - self._last_frame_monotonic, 2)
            if self._last_frame_monotonic is not None
            else None
        )
        status = self._status
        if age_seconds is not None and age_seconds >= self._unhealthy_no_frame_seconds and status == "healthy":
            status = "degraded"
        if self._reconnect_attempts >= self._failed_reconnect_threshold and status == "reconnecting":
            status = "failed"
        return {
            "camera_id": self.camera_id,
            "status": status,
            "source_type": self.source_type,
            "last_frame_at": self._last_frame_at,
            "last_source_timestamp": self._last_source_timestamp,
            "source_base_timestamp": (
                self._file_source_started_at.isoformat() if self._file_source_started_at is not None else None
            ),
            "fps_decode": self.fps_decode,
            "latency_ms": self.average_read_latency_ms,
            "reconnect_attempts": self._reconnect_attempts,
            "frames_decoded_total": self._frames_decoded_total,
            "offline_transitions_total": self._offline_transitions,
            "online_transitions_total": self._online_transitions,
            "age_seconds": age_seconds,
            "last_error": self._last_error,
        }

    def _capture_source(self) -> Any:
        if self.source_type == "webcam":
            text = str(self.source)
            return int(text) if text.isdigit() else self.source
        return self.source

    def _wait_for_reconnect(self, stop_event: threading.Event) -> bool:
        self.close()
        if not self._reconnect_enabled or self.source_type == "file":
            self._mark_state("failed", self._last_error or "reconnect disabled")
            return False

        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._reconnect_max_attempts:
            self._mark_state("failed", self._last_error or "reconnect attempts exhausted")
            return False

        backoff = min(
            self._reconnect_max_backoff_seconds,
            self._reconnect_initial_backoff_seconds * (2 ** max(0, self._reconnect_attempts - 1)),
        )
        if self._reconnect_jitter:
            backoff = backoff * random.uniform(0.8, 1.2)
        deadline = time.monotonic() + backoff
        while time.monotonic() < deadline:
            if stop_event.is_set():
                return False
            time.sleep(0.1)
        return True

    def _mark_state(self, status: str, error: str | None) -> None:
        if status == "reconnecting" and self._status != "reconnecting":
            self._offline_transitions += 1
        self._status = status
        self._last_error = error
        if error:
            logger.warning("RTSPIngestService[%s] %s: %s", self.camera_id, status, error)

    def _normalized_timestamp(self) -> str:
        if self._timestamp_source == "system":
            return _now_iso()
        source_ts = self._source_timestamp()
        if source_ts is None:
            return _now_iso()
        try:
            parsed = datetime.fromisoformat(source_ts)
            skew_ms = abs((datetime.now(timezone.utc) - parsed).total_seconds() * 1000.0)
            if skew_ms > self._max_clock_skew_ms:
                return _now_iso()
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            return _now_iso()

    def _source_timestamp(self) -> str | None:
        if self.source_type == "file" and self._capture is not None:
            try:
                pos_msec = float(self._capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            except Exception:
                pos_msec = 0.0
            if pos_msec >= 0 and self._file_source_started_at is not None:
                seconds = pos_msec / 1000.0
                return datetime.fromtimestamp(
                    self._file_source_started_at.timestamp() + seconds,
                    timezone.utc,
                ).isoformat()
        return None

    def _update_preview(self, frame: np.ndarray) -> None:
        try:
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        except Exception:
            return
        if not ok:
            return
        with self._preview_lock:
            self._latest_preview_jpeg = encoded.tobytes()
            self._latest_preview_at = self._last_frame_at
