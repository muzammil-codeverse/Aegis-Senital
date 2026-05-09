from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import List

import cv2
import numpy as np

from core.event_bus import get_event_bus
from core.runtime import get_runtime_supervisor
from inference.context.context_engine import ContextEngine
from inference.detection_engine import DetectionEngine
from inference.event_buffer import EventBuffer
from inference.event_engine import EventEngine
from inference.metrics import metrics
from inference.model_pool import ModelPool
from inference.monitoring.metrics import register_stream, get_stream_metrics, get_metrics
from inference.runtime import get_intelligence_runtime
from inference.scenario_engine import ScenarioEngine
from inference.schemas import FramePacket
from inference.tracker import MultiObjectTracker
from inference.validation.pipeline_validator import validate_frame_result

logger = logging.getLogger(__name__)

_RESIZE_DIM = (640, 640)

# ── adaptive batch sizing ──────────────────────────────────────────────────────
_BATCH_SIZE_INIT = 4
_BATCH_SIZE_MIN = 2
_BATCH_SIZE_MAX = 8
_BATCH_GROW_THRESHOLD_MS = 60.0     # per-frame ms below this → grow batch by 1
_BATCH_SHRINK_THRESHOLD_MS = 100.0  # per-frame ms above this → shrink batch by 1

# ── 3-thread pipeline queue sizes ─────────────────────────────────────────────
_INGEST_QUEUE_MAXSIZE = 32   # raw frames between ingest and inference threads
_RESULT_QUEUE_MAXSIZE = 64   # FramePackets between inference and postproc threads

# ── result-queue priority levels (lower = higher priority) ────────────────────
_PRIORITY_WEAPON = 3    # at least one weapon-class detection
_PRIORITY_PERSON = 5    # persons present, no weapons
_PRIORITY_EMPTY = 9     # no significant detections

# ── Phase 6: circuit breaker constants ───────────────────────────────────────
_CB_FAILURE_WINDOW = 60          # rolling window in frames for failure-rate check
_CB_FAILURE_THRESHOLD = 0.50     # ≥50% failure rate in window trips the rate breaker
_CB_EVENT_RATE_WINDOW = 10.0     # seconds for event-rate check
_CB_EVENT_RATE_THRESHOLD = 100   # events/sec sustained over the window trips breaker
_CB_COOLDOWN = 30.0              # seconds before an OPEN breaker moves to HALF_OPEN

# ── Phase 6: latency budget ───────────────────────────────────────────────────
_MAX_PIPELINE_MS = 100.0         # target end-to-end per-frame budget (milliseconds)
DETERMINISTIC_MODE = os.getenv("AEGIS_DETERMINISTIC", "0") == "1"

# Weapon labels for priority scoring (must match event_engine.WEAPON_LABELS)
_WEAPON_LABELS = frozenset({
    "weapon", "pistol", "rifle", "knife", "grenade", "gun", "shotgun", "sword",
})


def _frame_priority(packet: FramePacket) -> int:
    """Assign a result-queue priority to a FramePacket based on detections."""
    classes = {d.class_name for d in packet.detections}
    if classes & _WEAPON_LABELS:
        return _PRIORITY_WEAPON
    if "person" in classes:
        return _PRIORITY_PERSON
    return _PRIORITY_EMPTY


def _packet_timestamp_float(packet: FramePacket) -> float:
    try:
        return float(packet.timestamp)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(packet.timestamp)).timestamp()
    except ValueError:
        return time.time()


# ── Circuit Breaker ───────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Thread-safe three-state fault isolator: CLOSED → OPEN → HALF_OPEN → CLOSED.

    State machine:
        CLOSED    — normal operation; failures increment the counter; success
                    resets it.  When failures reach failure_threshold the
                    breaker transitions to OPEN.
        OPEN      — all requests are blocked.  After reset_timeout seconds
                    the breaker moves to HALF_OPEN.
        HALF_OPEN — one probe request is allowed through.  If it succeeds
                    the breaker closes; if it fails the breaker re-opens.

    All mutations are protected by an internal Lock so the breaker can be
    read from the postproc thread while being written from the inference thread.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 10.0,
    ) -> None:
        self._lock = threading.Lock()
        self.failures: int = 0
        self.failure_threshold: int = failure_threshold
        self.last_failure_time: float | None = None
        self.reset_timeout: float = reset_timeout
        self.state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
                self.last_failure_time = None
            elif self.state == "CLOSED":
                self.failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.monotonic()
            if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
                self.state = "OPEN"

    def check_and_transition(self) -> None:
        """Evaluate OPEN → HALF_OPEN timeout transition.  Call once per batch cycle."""
        with self._lock:
            if self.state == "OPEN" and self.last_failure_time is not None:
                if time.monotonic() - self.last_failure_time >= self.reset_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("CircuitBreaker: OPEN → HALF_OPEN (probe allowed)")

    def force_open(self) -> None:
        with self._lock:
            self.state = "OPEN"
            self.last_failure_time = time.monotonic()
            self.failures = self.failure_threshold

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    @property
    def allows_request(self) -> bool:
        return self.state in ("CLOSED", "HALF_OPEN")


# ── StreamProcessor ───────────────────────────────────────────────────────────

class StreamProcessor:
    """
    Self-contained per-stream inference pipeline — three decoupled threads.

    Thread 1 — ingest (_ingest_loop):
        Opens the capture source, reads frames, resizes them to 640×640, and
        pushes (frame_id, frame) tuples to _ingest_queue (bounded Queue,
        maxsize=32).  Drops frames immediately when the queue is full rather
        than blocking.  Obeys the _skip_next_event signal set by the inference
        thread when the pipeline is running over the latency budget.

    Thread 2 — inference (_inference_loop / _run_batch):
        Pops frames from _ingest_queue and accumulates them into variable-size
        batches (_batch_size, starting at 4, range 2–8).  On a full batch a
        single predict_batch() GPU call is issued.  Each resulting FramePacket
        is scored for priority (weapon → 3, person → 5, empty → 9) and pushed
        to _result_queue (PriorityQueue, maxsize=64) so the postproc thread
        handles high-severity frames first.  Adaptive batch sizing:
            per-frame ms < 60  → grow batch size (up to 8)
            per-frame ms > 100 → shrink batch size (down to 2)
        Sets _skip_next_event when per-frame ms > _MAX_PIPELINE_MS so the
        ingest thread drops the next frame to relieve GPU pressure.

    Thread 3 — post-processing (_postproc_loop):
        Drains _result_queue in priority order.  For each packet runs:
        fusion → tracking → context annotation → event buffer → event engine
        → scenario engine → EventBus publish.

    Both single-frame and batch inference modes are routed through the same
    three-thread architecture.  Shutdown propagates via sentinel None values
    pushed through each queue in order (ingest → inference → postproc).

    Circuit breaker (thread-safe, CLOSED/OPEN/HALF_OPEN):
        5 consecutive inference failures → OPEN.  After _CB_COOLDOWN seconds
        → HALF_OPEN (one probe).  Also tripped by a rate-based secondary check
        (_check_circuit_breaker): ≥50% failure rate over 60 frames, or
        event rate > 100/s over 10 seconds.

    Lifecycle:
        proc = StreamProcessor("cam_01", "rtsp://…", model_pool)
        proc.start()
        …
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
        self._intelligence_runtime = get_intelligence_runtime()
        self._runtime_supervisor = get_runtime_supervisor()

        # ── 3-thread pipeline queues ──────────────────────────────────────────
        self._ingest_queue: queue.Queue = queue.Queue(maxsize=_INGEST_QUEUE_MAXSIZE)
        self._result_queue: queue.PriorityQueue = queue.PriorityQueue(
            maxsize=_RESULT_QUEUE_MAXSIZE
        )

        # ── adaptive batch state (written by inference thread only) ───────────
        self._batch_size: int = 4 if DETERMINISTIC_MODE else _BATCH_SIZE_INIT
        self._batch_seq: int = 0
        self._seq_lock: threading.Lock = threading.Lock()

        # ── inter-thread latency signals ──────────────────────────────────────
        # Set by inference thread; cleared by ingest thread after dropping a frame.
        self._skip_next_event: threading.Event = threading.Event()
        # Written by inference thread, read by postproc thread (GIL-safe bool).
        self._skip_context_next: bool = False

        # ── thread control ────────────────────────────────────────────────────
        self._stop_event = threading.Event()
        self._status: str = "idle"
        self._ingest_thread: threading.Thread | None = None
        self._inference_thread: threading.Thread | None = None
        self._postproc_thread: threading.Thread | None = None

        # ── Phase 6: circuit breaker ──────────────────────────────────────────
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            reset_timeout=_CB_COOLDOWN,
        )
        self._cb_frame_results: deque[bool] = deque(maxlen=_CB_FAILURE_WINDOW)
        self._cb_event_times: deque[float] = deque(maxlen=2000)
        self._recent_pipeline_ms: deque[float] = deque(maxlen=20)

        # ── per-stream metrics ────────────────────────────────────────────────
        register_stream(stream_id)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the three pipeline threads and begin processing."""
        if self._ingest_thread is not None and self._ingest_thread.is_alive():
            logger.warning("StreamProcessor '%s' already running", self.stream_id)
            return
        self._stop_event.clear()
        self._status = "starting"

        self._postproc_thread = threading.Thread(
            target=self._postproc_loop,
            name=f"stream-{self.stream_id}-postproc",
            daemon=True,
        )
        self._inference_thread = threading.Thread(
            target=self._inference_loop,
            name=f"stream-{self.stream_id}-inference",
            daemon=True,
        )
        self._ingest_thread = threading.Thread(
            target=self._ingest_loop,
            name=f"stream-{self.stream_id}-ingest",
            daemon=True,
        )
        # Start in reverse dependency order so downstream threads are ready first.
        self._postproc_thread.start()
        self._inference_thread.start()
        self._ingest_thread.start()

        logger.info(
            json.dumps({
                "event": "stream_started",
                "stream_id": self.stream_id,
                "source": self.source,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )

    def stop(self) -> None:
        """Signal all three threads to stop and wait for them to exit."""
        self._stop_event.set()
        # Unblock any thread waiting on an empty ingest queue.
        for _ in range(3):
            try:
                self._ingest_queue.put_nowait(None)
            except queue.Full:
                pass
        for thread in (self._ingest_thread, self._inference_thread, self._postproc_thread):
            if thread is not None:
                thread.join(timeout=10.0)
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
            self._ingest_thread is not None
            and self._ingest_thread.is_alive()
            and not self._stop_event.is_set()
        )

    def get_status(self) -> dict:
        sm = get_stream_metrics(self.stream_id)
        return {
            "stream_id": self.stream_id,
            "source": self.source,
            "status": self._status,
            "running": self.is_running,
            "circuit_state": self._circuit_breaker.state,
            "circuit_open": self._circuit_breaker.is_open,
            "batch_size": self._batch_size,
            "ingest_queue_depth": self._ingest_queue.qsize(),
            "result_queue_depth": self._result_queue.qsize(),
            "metrics": sm.snapshot() if sm else {},
        }

    # ── Thread 1: frame ingestion ─────────────────────────────────────────────

    def _ingest_loop(self) -> None:
        """
        Read frames from the capture source and push them to _ingest_queue.

        Respects the _skip_next_event signal: when the inference thread sets it
        (because the batch was slow), the next readable frame is discarded rather
        than enqueued.  Frames are also silently dropped when _ingest_queue is
        full so the ingest thread never blocks the capture loop.
        """
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            logger.error(
                "StreamProcessor '%s': cannot open source '%s'",
                self.stream_id, self.source,
            )
            self._status = "error"
            self._ingest_queue.put(None)  # propagate sentinel so downstream exits
            return

        _is_file = isinstance(self.source, str) and self.source.lower().endswith(
            (".mp4", ".avi", ".mov", ".mkv", ".webm")
        )
        frame_id = 0
        self._status = "running"

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    if _is_file:
                        break  # end of file — flush then exit
                    time.sleep(0.05)  # live camera blip: retry
                    continue

                # Latency-budget drop: inference thread signalled us to shed load.
                if self._skip_next_event.is_set():
                    self._skip_next_event.clear()
                    get_metrics().record_frame_dropped()
                    metrics.frames_dropped += 1
                    get_metrics().record_latency_violation()
                    logger.debug(
                        "StreamProcessor '%s': frame %d dropped — latency budget signal",
                        self.stream_id, frame_id,
                    )
                    frame_id += 1
                    continue

                resized = cv2.resize(frame, _RESIZE_DIM)
                try:
                    self._ingest_queue.put_nowait((frame_id, resized))
                except queue.Full:
                    get_metrics().record_frame_dropped()
                    metrics.frames_dropped += 1
                frame_id += 1

        finally:
            cap.release()

        # Send sentinel to unblock the inference thread.
        self._ingest_queue.put(None)

    # ── Thread 2: batched GPU inference ──────────────────────────────────────

    def _inference_loop(self) -> None:
        """
        Accumulate frames from _ingest_queue into variable-size batches and
        dispatch each full batch to _run_batch().  Propagates shutdown sentinel.
        """
        batch_frames: List[np.ndarray] = []
        batch_ids: List[int] = []

        def _flush() -> None:
            if batch_frames:
                self._run_batch(list(batch_frames), list(batch_ids))
                batch_frames.clear()
                batch_ids.clear()

        while True:
            try:
                item = self._ingest_queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    _flush()
                    self._result_queue.put(None)
                    break
                continue

            if item is None:
                _flush()
                self._result_queue.put(None)
                break

            fid, frame = item
            batch_frames.append(frame)
            batch_ids.append(fid)

            if len(batch_frames) < self._batch_size:
                continue  # keep filling the batch

            _flush()

    def _run_batch(self, frames: List[np.ndarray], frame_ids: List[int]) -> None:
        """
        Run a single predict_batch() GPU call, adaptively resize the batch,
        enforce the latency budget, and enqueue resulting packets by priority.
        """
        self._circuit_breaker.check_and_transition()
        if not frames:
            return
        if self._circuit_breaker.is_open:
            get_metrics().record_frame_dropped(len(frames))
            metrics.frames_dropped += len(frames)
            return

        t0 = time.monotonic()
        try:
            packets = self._engine.predict_batch(frames, frame_ids, self.stream_id)
            batch_ms = (time.monotonic() - t0) * 1000.0
            n = max(1, len(frames))
            per_frame_ms = batch_ms / n

            # Adaptive batch size: grow when fast, shrink when slow.
            if not DETERMINISTIC_MODE:
                if per_frame_ms < _BATCH_GROW_THRESHOLD_MS:
                    self._batch_size = min(_BATCH_SIZE_MAX, self._batch_size + 1)
                elif per_frame_ms > _BATCH_SHRINK_THRESHOLD_MS:
                    self._batch_size = max(_BATCH_SIZE_MIN, self._batch_size - 1)

            # Latency budget: signal ingest to drop the next frame.
            if per_frame_ms > _MAX_PIPELINE_MS:
                self._skip_next_event.set()
                logger.warning(
                    "StreamProcessor '%s': per-frame %.1f ms > budget %.1f ms "
                    "— dropping next frame",
                    self.stream_id, per_frame_ms, _MAX_PIPELINE_MS,
                )

            # Update rolling latency and context-suppression flag.
            self._recent_pipeline_ms.append(per_frame_ms)
            avg_ms = (
                sum(self._recent_pipeline_ms) / len(self._recent_pipeline_ms)
                if self._recent_pipeline_ms else 0.0
            )
            metrics.avg_latency_ms = avg_ms
            metrics.max_latency_ms = max(metrics.max_latency_ms, per_frame_ms)
            self._skip_context_next = avg_ms > _MAX_PIPELINE_MS

            # Score and enqueue each packet with priority for postproc ordering.
            for packet in packets:
                priority = _frame_priority(packet)
                with self._seq_lock:
                    seq = self._batch_seq
                    self._batch_seq += 1
                try:
                    self._result_queue.put_nowait((priority, seq, packet))
                except queue.Full:
                    get_metrics().record_queue_overflow()
                    metrics.queue_overflows += 1

            sm = get_stream_metrics(self.stream_id)
            if sm is not None:
                sm.record_frame(batch_ms / 1000.0)
            self._runtime_supervisor.report_inference_latency(per_frame_ms)

            self._circuit_breaker.record_success()
            self._cb_frame_results.append(True)
            metrics.frames_processed += len(packets)

        except Exception as exc:
            logger.error({"stage": "inference", "error": str(exc), "frame_id": frame_ids[0] if frame_ids else None})
            sm = get_stream_metrics(self.stream_id)
            if sm is not None:
                sm.record_failure()
            self._circuit_breaker.record_failure()
            self._cb_frame_results.append(False)

        self._check_circuit_breaker()

    # ── Thread 3: tracking, events, publish ───────────────────────────────────

    def _postproc_loop(self) -> None:
        """
        Drain _result_queue in priority order (weapon frames first) and run
        the full post-detection pipeline for each FramePacket.
        """
        bus = get_event_bus()

        while True:
            try:
                item = self._result_queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue

            if item is None:
                break

            _, _, packet = item
            try:
                self._process_packet(packet, bus)
            except Exception as exc:
                logger.warning(
                    "StreamProcessor '%s': postproc failed for frame %d: %s",
                    self.stream_id, packet.frame_id, exc,
                )

    # ── per-frame post-detection pipeline ────────────────────────────────────

    def _process_packet(self, packet: FramePacket, bus: object) -> None:
        """
        Run the tracking → trajectory → anomaly → event → incident pipeline for one FramePacket whose
        detections have already been populated by predict_batch().
        """
        # Stage 2: model-level fusion (NMS across weapon+phone detections)
        packet.detections = self._fusion_engine.fuse(
            packet.detections,
            active_tracks=self._tracker.get_active_tracks(self.stream_id),
        )
        if DETERMINISTIC_MODE:
            packet.detections = sorted(packet.detections, key=lambda d: d.detection_id)

        # Stage 3: per-stream tracking
        packet.tracks = self._tracker.update(packet)
        ts_float = _packet_timestamp_float(packet)

        # Stage 3a: trajectory intelligence and anomaly analysis
        trajectories = [
            self._intelligence_runtime.trajectory_engine.update(track, timestamp=ts_float)
            for track in packet.tracks
            if track.missed_frames == 0
        ]
        anomalies = self._intelligence_runtime.anomaly_engine.evaluate_trajectories(
            trajectories,
            camera_id=packet.camera_id,
            frame_id=packet.frame_id,
            timestamp=ts_float,
        )

        # Stage 3b: context annotation — suppressed when pipeline is over budget
        if not self._skip_context_next:
            ctx_count = self._context_engine.annotate(packet)
            if ctx_count:
                get_metrics().record_context_annotation(ctx_count)

        # Stage 4: buffer + temporal scoring
        self._buffer.add(packet)
        events = self._event_engine.evaluate(self._buffer)
        scenarios = self._scenario_engine.aggregate(events)
        validate_frame_result(packet, packet.tracks, events)

        # Stage 6: incident reasoning, cross-camera handoff, forensic metadata
        intelligence_packet = self._intelligence_runtime.process_frame_context(
            camera_id=packet.camera_id,
            frame_id=packet.frame_id,
            timestamp=ts_float,
            detections=packet.detections,
            tracks=packet.tracks,
            trajectories=trajectories,
            anomalies=anomalies,
            events=events,
        )
        packet.metadata["intelligence"] = intelligence_packet

        _snapshot_dir = os.getenv("AEGIS_DEBUG_SNAPSHOT_DIR", "")
        if _snapshot_dir:
            os.makedirs(_snapshot_dir, exist_ok=True)
            _snap_path = os.path.join(_snapshot_dir, f"frame_{packet.frame_id}.json")
            with open(_snap_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "frame_id": packet.frame_id,
                        "detections": [d.to_dict() for d in packet.detections],
                        "tracks": [t.to_dict() for t in packet.tracks],
                        "trajectories": trajectories,
                        "anomalies": anomalies,
                        "events": [e.to_dict() for e in events],
                        "incidents": intelligence_packet.get("incidents", []),
                    },
                    f,
                )

        # Update frame snapshot service with latest detections/tracks (best-effort)
        try:
            from app.services.frame_snapshot_service import get_frame_snapshot_service
            track_dicts = [
                {
                    "type": getattr(t, "class_name", ""),
                    "bbox": list(getattr(t, "bbox", [])),
                    "confidence": float(getattr(t, "confidence", 0.0)),
                    "track_id": getattr(t, "track_id", None),
                }
                for t in packet.tracks
                if getattr(t, "missed_frames", 0) == 0 and len(getattr(t, "bbox", [])) == 4
            ]
            det_dicts = [
                {
                    "type": getattr(d, "class_name", ""),
                    "bbox": list(getattr(d, "bbox", [])),
                    "confidence": float(getattr(d, "confidence", 0.0)),
                }
                for d in packet.detections[:20]
            ]
            incidents = intelligence_packet.get("incidents", [])[:3] if intelligence_packet else []
            event_dicts = [e.to_dict() if hasattr(e, "to_dict") else dict(e) for e in events[:5]]
            get_frame_snapshot_service().update_latest_frame(
                camera_id=packet.camera_id,
                frame_id=packet.frame_id,
                timestamp=ts_float,
                detections=det_dicts,
                tracks=track_dicts,
                events=event_dicts,
                incidents=incidents,
            )
        except Exception:
            pass

        # Stage 5: publish to central EventBus
        now = time.monotonic()
        for event in events:
            bus.publish_event(event, stream_id=self.stream_id)
            self._cb_event_times.append(now)

        logger.debug(
            json.dumps({
                "event": "stream_frame_processed",
                "stream_id": self.stream_id,
                "frame_id": packet.frame_id,
                "detections": len(packet.detections),
                "tracks": len(packet.tracks),
                "events": len(events),
                "anomalies": len(anomalies),
                "incidents": len(intelligence_packet.get("incidents", [])),
                "scenarios": len(scenarios),
                "context_skipped": self._skip_context_next,
                "circuit_state": self._circuit_breaker.state,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )

    # ── circuit breaker (rate-based secondary check) ──────────────────────────

    def _check_circuit_breaker(self) -> None:
        """
        Trip the circuit breaker if the sustained failure rate or event rate
        exceeds thresholds.  Complements the consecutive-failure CircuitBreaker
        class by catching episodic (non-consecutive) overload patterns.
        """
        if self._circuit_breaker.is_open:
            return

        # Failure-rate check over rolling window
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
        self._circuit_breaker.force_open()
        self._runtime_supervisor.report_circuit_breaker(self.stream_id, self._circuit_breaker.state)
        get_metrics().record_circuit_break()
        metrics.circuit_breaker_trips += 1
        logger.critical(
            json.dumps({
                "event": "circuit_breaker_tripped",
                "stream_id": self.stream_id,
                "reason": reason,
                "cooldown_seconds": _CB_COOLDOWN,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        )
