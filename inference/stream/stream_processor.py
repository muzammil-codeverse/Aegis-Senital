from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np

from inference.context.context_engine import ContextEngine
from inference.detection_engine import DetectionEngine
from inference.event_buffer import EventBuffer
from inference.event_bus import get_event_bus
from inference.event_engine import EventEngine
from inference.model_pool import ModelPool
from inference.monitoring.metrics import register_stream, get_stream_metrics, get_metrics
from inference.scenario_engine import ScenarioEngine
from inference.tracker import MultiObjectTracker

logger = logging.getLogger(__name__)

_RESIZE_DIM = (640, 640)

# ── Phase 6: circuit breaker constants ───────────────────────────────────────
_CB_FAILURE_WINDOW = 60          # rolling window in frames for failure-rate check
_CB_FAILURE_THRESHOLD = 0.50     # ≥50% failure rate in window trips the breaker
_CB_EVENT_RATE_WINDOW = 10.0     # seconds for event-rate check
_CB_EVENT_RATE_THRESHOLD = 100   # events/sec sustained over the window trips breaker
_CB_COOLDOWN = 30.0              # seconds before a tripped breaker resets

# ── Phase 6: latency budget ───────────────────────────────────────────────────
_MAX_PIPELINE_MS = 100.0         # target end-to-end frame budget (milliseconds)


class StreamProcessor:
    """
    Self-contained per-stream inference pipeline.

    Each instance owns its own DetectionEngine (backed by the shared ModelPool),
    MultiObjectTracker, EventBuffer, EventEngine, and ScenarioEngine.  No
    mutable state is shared with other streams.

    The pipeline mirrors video_service._process_frame_job:
        1. Resize frame
        2. Detect   — pool-guarded GPU inference
        3. Track    — per-stream tracker, no global lock
        4. Buffer   — per-stream EventBuffer
        5. Evaluate — per-stream EventEngine → Events
        6. Publish  — Events pushed to central EventBus

    Phase-6 hardening:
        Circuit breaker — auto-disables the stream if the sustained failure rate
        exceeds _CB_FAILURE_THRESHOLD or the event rate exceeds
        _CB_EVENT_RATE_THRESHOLD events/sec.  The breaker resets automatically
        after _CB_COOLDOWN seconds.

        Latency budget — if a frame's pipeline time exceeds _MAX_PIPELINE_MS,
        a latency_violation is recorded.  Context annotation is skipped on the
        next frame to shed load when latency is consistently over budget.

    Lifecycle:
        proc = StreamProcessor("cam_01", "rtsp://...")
        proc.start()
        ...
        proc.stop()
    """

    def __init__(self, stream_id: str, source: str, model_pool: ModelPool) -> None:
        if not model_pool.is_loaded:
            raise RuntimeError(
                f"StreamProcessor '{stream_id}': ModelPool must be loaded before creating streams"
            )

        self.stream_id = stream_id
        self.source = source

        # ── per-stream inference components (isolated, no shared state) ───────
        self._engine = DetectionEngine(model_pool=model_pool)

        from inference.identity_db import get_db
        from inference.identity_fusion_engine import IdentityFusionEngine
        from inference.model_fusion_engine import ModelFusionEngine

        _db = get_db()
        _fusion = IdentityFusionEngine(db=_db)
        self._tracker = MultiObjectTracker(db=_db, identity_fusion=_fusion)
        self._buffer = EventBuffer(maxlen=60, window=10, min_consecutive=3)
        self._event_engine = EventEngine(db=_db)
        self._fusion_engine = ModelFusionEngine()
        self._scenario_engine = ScenarioEngine(db=_db)
        self._context_engine = ContextEngine()

        # ── thread control ────────────────────────────────────────────────────
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status: str = "idle"

        # ── Phase 6: circuit breaker state ───────────────────────────────────
        self._circuit_open: bool = False
        self._circuit_tripped_at: float = 0.0
        self._cb_frame_results: deque[bool] = deque(maxlen=_CB_FAILURE_WINDOW)
        self._cb_event_times: deque[float] = deque(maxlen=2000)

        # ── Phase 6: latency budget tracking ─────────────────────────────────
        # Rolling window of recent pipeline times (ms) — used to detect
        # sustained overload and decide whether to shed context annotation load.
        self._recent_pipeline_ms: deque[float] = deque(maxlen=20)
        self._skip_context_next: bool = False

        # ── per-stream metrics ────────────────────────────────────────────────
        register_stream(stream_id)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the processing thread and begin reading frames."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("StreamProcessor '%s' already running", self.stream_id)
            return
        self._stop_event.clear()
        self._status = "starting"
        self._thread = threading.Thread(
            target=self._run,
            name=f"stream-{self.stream_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            json.dumps({
                "event": "stream_started",
                "stream_id": self.stream_id,
                "source": self.source,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )

    def stop(self) -> None:
        """Signal the processing thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._status = "stopped"
        logger.info(
            json.dumps({
                "event": "stream_stopped",
                "stream_id": self.stream_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )

    @property
    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_event.is_set()
        )

    def get_status(self) -> dict:
        sm = get_stream_metrics(self.stream_id)
        return {
            "stream_id": self.stream_id,
            "source": self.source,
            "status": self._status,
            "running": self.is_running,
            "circuit_open": self._circuit_open,
            "metrics": sm.snapshot() if sm else {},
        }

    # ── main processing loop ──────────────────────────────────────────────────

    def _run(self) -> None:
        self._status = "running"
        cap = cv2.VideoCapture(self.source)

        if not cap.isOpened():
            logger.error(
                "StreamProcessor '%s': cannot open source '%s'",
                self.stream_id, self.source,
            )
            self._status = "error"
            return

        sm = get_stream_metrics(self.stream_id)
        bus = get_event_bus()
        frame_id = 0
        _is_file = isinstance(self.source, str) and self.source.lower().endswith(
            (".mp4", ".avi", ".mov", ".mkv", ".webm")
        )

        try:
            while not self._stop_event.is_set():
                # ── circuit breaker guard ─────────────────────────────────────
                if self._circuit_open:
                    now = time.monotonic()
                    if now - self._circuit_tripped_at >= _CB_COOLDOWN:
                        self._circuit_open = False
                        logger.info(
                            "StreamProcessor '%s': circuit breaker reset after cooldown",
                            self.stream_id,
                        )
                    else:
                        time.sleep(0.1)
                        continue

                ret, frame = cap.read()

                if not ret:
                    if _is_file:
                        break  # end of file
                    # Live camera lost: brief pause then retry
                    time.sleep(0.05)
                    continue

                t0 = time.monotonic()
                try:
                    self._process_frame(frame, frame_id, bus)
                    pipeline_ms = (time.monotonic() - t0) * 1000.0
                    self._recent_pipeline_ms.append(pipeline_ms)
                    if sm is not None:
                        sm.record_frame(pipeline_ms / 1000.0)
                    self._cb_frame_results.append(True)

                    # Latency violation
                    if pipeline_ms > _MAX_PIPELINE_MS:
                        get_metrics().record_latency_violation()
                        logger.debug(
                            "StreamProcessor '%s': frame %d exceeded latency budget "
                            "(%.1fms > %.1fms)",
                            self.stream_id, frame_id, pipeline_ms, _MAX_PIPELINE_MS,
                        )

                    # Flag context annotation to be skipped next frame when avg
                    # pipeline time is consistently over budget (shed load).
                    avg_ms = (
                        sum(self._recent_pipeline_ms) / len(self._recent_pipeline_ms)
                        if self._recent_pipeline_ms else 0.0
                    )
                    self._skip_context_next = avg_ms > _MAX_PIPELINE_MS

                except Exception as exc:
                    logger.warning(
                        "StreamProcessor '%s': frame %d failed: %s",
                        self.stream_id, frame_id, exc,
                    )
                    if sm is not None:
                        sm.record_failure()
                    self._cb_frame_results.append(False)

                self._check_circuit_breaker()
                frame_id += 1
        finally:
            cap.release()
            self._status = "stopped"

    # ── circuit breaker ───────────────────────────────────────────────────────

    def _check_circuit_breaker(self) -> None:
        """Trip the circuit breaker if failure rate or event rate exceeds thresholds."""
        if self._circuit_open:
            return

        # Failure-rate check
        n = len(self._cb_frame_results)
        if n >= _CB_FAILURE_WINDOW // 2:
            failure_rate = sum(1 for r in self._cb_frame_results if not r) / n
            if failure_rate >= _CB_FAILURE_THRESHOLD:
                self._trip_circuit_breaker(
                    f"failure rate {failure_rate:.0%} >= {_CB_FAILURE_THRESHOLD:.0%}"
                )
                return

        # Event-rate check
        now = time.monotonic()
        cutoff = now - _CB_EVENT_RATE_WINDOW
        while self._cb_event_times and self._cb_event_times[0] < cutoff:
            self._cb_event_times.popleft()
        events_per_sec = len(self._cb_event_times) / _CB_EVENT_RATE_WINDOW
        if events_per_sec > _CB_EVENT_RATE_THRESHOLD:
            self._trip_circuit_breaker(
                f"event rate {events_per_sec:.1f}/s > {_CB_EVENT_RATE_THRESHOLD}/s"
            )

    def _trip_circuit_breaker(self, reason: str) -> None:
        self._circuit_open = True
        self._circuit_tripped_at = time.monotonic()
        get_metrics().record_circuit_break()
        logger.critical(
            json.dumps({
                "event": "circuit_breaker_tripped",
                "stream_id": self.stream_id,
                "reason": reason,
                "cooldown_seconds": _CB_COOLDOWN,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )

    # ── main processing pipeline ──────────────────────────────────────────────

    def _process_frame(self, frame: np.ndarray, frame_id: int, bus: object) -> None:
        resized = cv2.resize(frame, _RESIZE_DIM)

        # Stage 1: detection via shared ModelPool (GPU semaphore inside pool)
        packet = self._engine.predict(resized, frame_id=frame_id, camera_id=self.stream_id)

        # Stage 2: model-level fusion (NMS across weapon+phone detections)
        packet.detections = self._fusion_engine.fuse(
            packet.detections,
            active_tracks=self._tracker.get_active_tracks(self.stream_id),
        )

        # Stage 3: per-stream tracking (own state — no global lock needed)
        packet.tracks = self._tracker.update(packet)

        # Stage 3b: context annotation — skipped when pipeline is over budget
        # to shed load.  The flag is set/cleared by the run loop based on
        # rolling average pipeline time vs _MAX_PIPELINE_MS.
        if not self._skip_context_next:
            ctx_count = self._context_engine.annotate(packet)
            if ctx_count:
                get_metrics().record_context_annotation(ctx_count)

        # Stage 4: buffer + temporal scoring
        self._buffer.add(packet)
        events = self._event_engine.evaluate(self._buffer)
        scenarios = self._scenario_engine.aggregate(events)

        # Stage 5: publish to central EventBus
        now = time.monotonic()
        for event in events:
            bus.publish_event(event, stream_id=self.stream_id)
            self._cb_event_times.append(now)

        logger.debug(
            json.dumps({
                "event": "stream_frame_processed",
                "stream_id": self.stream_id,
                "frame_id": frame_id,
                "detections": len(packet.detections),
                "tracks": len(packet.tracks),
                "events": len(events),
                "scenarios": len(scenarios),
                "context_skipped": self._skip_context_next,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )
