from __future__ import annotations

import threading
import time
from collections import deque


class SystemMetrics:
    """
    Thread-safe cumulative counters for the Aegis Sentinel inference pipeline.

    Separate from system_state.SystemState (which tracks FPS, latency, health
    score).  This class tracks raw event counts and rolling timing windows.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.frames_processed: int = 0
        self.frames_failed: int = 0
        self.detections_count: int = 0
        self.events_generated: int = 0
        self.events_dropped: int = 0
        self._inference_times: deque[float] = deque(maxlen=100)
        self._tracking_times: deque[float] = deque(maxlen=100)
        self._pipeline_times: deque[float] = deque(maxlen=100)
        # Phase 5 — intelligence layer counters
        self._identity_conf_sum: float = 0.0
        self._identity_conf_count: int = 0
        self.context_annotations_count: int = 0
        self.high_priority_events: int = 0
        self.cross_stream_matches: int = 0
        # Phase 6 — hardening counters
        self.latency_violations: int = 0
        self.dropped_low_priority_events: int = 0
        self.expired_identities: int = 0
        self.stream_circuit_breaks: int = 0
        # Phase 7 — observability counters
        self.frames_dropped: int = 0          # frames skipped by latency budget
        self.queue_overflow_count: int = 0    # GPU queue full rejections
        # GPU utilisation estimate: ratio of cumulative inference seconds to wall seconds
        self._gpu_busy_seconds: float = 0.0
        self._gpu_wall_start: float = 0.0
        self._gpu_tracking_active: bool = False

    # ── counter increments ────────────────────────────────────────────────────

    def increment(self, counter: str, n: int = 1) -> None:
        if n < 0:
            raise ValueError("metrics increments must be non-negative")
        with self._lock:
            setattr(self, counter, getattr(self, counter, 0) + n)

    # ── timing recorders ──────────────────────────────────────────────────────

    def record_inference_time(self, seconds: float) -> None:
        with self._lock:
            self._inference_times.append(seconds)

    def record_tracking_time(self, seconds: float) -> None:
        with self._lock:
            self._tracking_times.append(seconds)

    def record_pipeline_time(self, seconds: float) -> None:
        with self._lock:
            self._pipeline_times.append(seconds)

    # ── Phase 5 intelligence recorders ───────────────────────────────────────

    def record_identity_confidence(self, score: float) -> None:
        with self._lock:
            self._identity_conf_sum += score
            self._identity_conf_count += 1

    def record_context_annotation(self, count: int = 1) -> None:
        with self._lock:
            self.context_annotations_count += count

    def record_high_priority_event(self, count: int = 1) -> None:
        with self._lock:
            self.high_priority_events += count

    def record_cross_stream_match(self, count: int = 1) -> None:
        with self._lock:
            self.cross_stream_matches += count

    # Phase 6 — hardening recorders

    def record_latency_violation(self) -> None:
        with self._lock:
            self.latency_violations += 1

    def record_dropped_event(self, count: int = 1) -> None:
        with self._lock:
            self.dropped_low_priority_events += count

    def record_expired_identity(self, count: int = 1) -> None:
        with self._lock:
            self.expired_identities += count

    def record_circuit_break(self) -> None:
        with self._lock:
            self.stream_circuit_breaks += 1

    def record_frame_dropped(self, count: int = 1) -> None:
        with self._lock:
            self.frames_dropped += count

    def record_queue_overflow(self, count: int = 1) -> None:
        with self._lock:
            self.queue_overflow_count += count

    def record_gpu_inference(self, busy_seconds: float) -> None:
        """Accumulate GPU busy time for utilisation estimate."""
        with self._lock:
            self._gpu_busy_seconds += busy_seconds
            if not self._gpu_tracking_active:
                self._gpu_wall_start = time.monotonic()
                self._gpu_tracking_active = True

    @property
    def gpu_util_estimate(self) -> float:
        """Rolling GPU utilisation in [0, 1]: busy_time / wall_time."""
        with self._lock:
            if not self._gpu_tracking_active or self._gpu_wall_start == 0.0:
                return 0.0
            wall = time.monotonic() - self._gpu_wall_start
            if wall <= 0.0:
                return 0.0
            return round(min(1.0, self._gpu_busy_seconds / wall), 4)

    @property
    def identity_confidence_avg(self) -> float:
        with self._lock:
            if self._identity_conf_count == 0:
                return 0.0
            return round(self._identity_conf_sum / self._identity_conf_count, 4)

    # ── rolling averages (computed lazily) ────────────────────────────────────

    @property
    def avg_inference_time(self) -> float:
        with self._lock:
            return (
                sum(self._inference_times) / len(self._inference_times)
                if self._inference_times else 0.0
            )

    @property
    def avg_tracking_time(self) -> float:
        with self._lock:
            return (
                sum(self._tracking_times) / len(self._tracking_times)
                if self._tracking_times else 0.0
            )

    @property
    def avg_pipeline_time(self) -> float:
        with self._lock:
            return (
                sum(self._pipeline_times) / len(self._pipeline_times)
                if self._pipeline_times else 0.0
            )

    # ── snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            def _avg_ms(q: deque) -> float:
                return round(sum(q) / len(q) * 1000.0, 2) if q else 0.0

            # Compute inline — calling the property would re-acquire self._lock
            # on the same thread and deadlock (threading.Lock is not reentrant).
            id_conf_avg = (
                round(self._identity_conf_sum / self._identity_conf_count, 4)
                if self._identity_conf_count > 0 else 0.0
            )

            return {
                "frames_processed": self.frames_processed,
                "frames_failed": self.frames_failed,
                "detections_count": self.detections_count,
                "events_generated": self.events_generated,
                "events_dropped": self.events_dropped,
                "avg_inference_time_ms": _avg_ms(self._inference_times),
                "avg_tracking_time_ms": _avg_ms(self._tracking_times),
                "avg_pipeline_time_ms": _avg_ms(self._pipeline_times),
                # Phase 5 — intelligence metrics
                "identity_confidence_avg": id_conf_avg,
                "context_annotations_count": self.context_annotations_count,
                "high_priority_events": self.high_priority_events,
                "cross_stream_matches": self.cross_stream_matches,
                # Phase 6 — hardening metrics
                "latency_violations": self.latency_violations,
                "dropped_low_priority_events": self.dropped_low_priority_events,
                "expired_identities": self.expired_identities,
                "stream_circuit_breaks": self.stream_circuit_breaks,
                # Phase 7 — observability metrics
                "frames_dropped": self.frames_dropped,
                "queue_overflow_count": self.queue_overflow_count,
                "gpu_util_estimate": (
                    round(min(1.0, self._gpu_busy_seconds / max(1e-9, time.monotonic() - self._gpu_wall_start)), 4)
                    if self._gpu_tracking_active else 0.0
                ),
                "latency_avg_ms": _avg_ms(self._pipeline_times),
            }


_metrics: SystemMetrics = SystemMetrics()


def get_metrics() -> SystemMetrics:
    """Return the process-wide SystemMetrics singleton."""
    return _metrics


# ── Per-stream metrics ─────────────────────────────────────────────────────────

class StreamMetrics:
    """
    Per-stream counters and rolling FPS tracker.

    One instance is created per stream via register_stream() and lives
    until deregister_stream() is called.  All mutations are lock-protected
    so producers (StreamProcessor threads) and consumers (API layer) can
    access concurrently without races.
    """

    def __init__(self, stream_id: str) -> None:
        self.stream_id = stream_id
        self._lock = threading.Lock()
        self.frames_processed: int = 0
        self.frames_failed: int = 0
        self.errors: int = 0
        self._fps_timestamps: deque[float] = deque(maxlen=30)
        self._pipeline_times: deque[float] = deque(maxlen=100)

    def record_frame(self, pipeline_time: float) -> None:
        """Record a successfully processed frame."""
        with self._lock:
            self.frames_processed += 1
            self._fps_timestamps.append(time.monotonic())
            self._pipeline_times.append(pipeline_time)

    def record_failure(self) -> None:
        """Record a frame that failed to process."""
        with self._lock:
            self.frames_failed += 1
            self.errors += 1

    @property
    def fps(self) -> float:
        """Rolling FPS computed over the last 30 frame timestamps."""
        with self._lock:
            if len(self._fps_timestamps) < 2:
                return 0.0
            elapsed = self._fps_timestamps[-1] - self._fps_timestamps[0]
            return round(len(self._fps_timestamps) / elapsed, 2) if elapsed > 0.0 else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            avg_ms = (
                round(sum(self._pipeline_times) / len(self._pipeline_times) * 1000.0, 2)
                if self._pipeline_times else 0.0
            )
            return {
                "stream_id": self.stream_id,
                "frames_processed": self.frames_processed,
                "frames_failed": self.frames_failed,
                "errors": self.errors,
                "fps": self.fps,
                "avg_pipeline_ms": avg_ms,
            }


# ── Stream metrics registry ────────────────────────────────────────────────────

_stream_registry: dict[str, StreamMetrics] = {}
_registry_lock: threading.Lock = threading.Lock()


def register_stream(stream_id: str) -> StreamMetrics:
    """Create and register a StreamMetrics instance.  Idempotent."""
    with _registry_lock:
        if stream_id not in _stream_registry:
            _stream_registry[stream_id] = StreamMetrics(stream_id)
        return _stream_registry[stream_id]


def get_stream_metrics(stream_id: str) -> StreamMetrics | None:
    """Return the StreamMetrics for stream_id, or None if not registered."""
    return _stream_registry.get(stream_id)


def deregister_stream(stream_id: str) -> None:
    """Remove metrics for a stopped stream."""
    with _registry_lock:
        _stream_registry.pop(stream_id, None)


def all_stream_snapshots() -> list[dict]:
    """Return metric snapshots for every currently registered stream."""
    with _registry_lock:
        streams = list(_stream_registry.values())
    return [sm.snapshot() for sm in streams]
