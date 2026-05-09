"""Phase 25 — End-to-end and per-stage latency profiling."""
from __future__ import annotations

import logging
import statistics
import time
from contextlib import contextmanager
from typing import Any

from backend.app.evaluation.schemas import LatencyMetricResult, LatencyStageResult

logger = logging.getLogger(__name__)

LATENCY_STAGES = [
    "frame_decode",
    "preprocessing",
    "yolo_inference",
    "open_vocab_inference",
    "tracking",
    "face_embedding",
    "reid_embedding",
    "identity_fusion",
    "event_scoring",
    "event_bus_publish",
    "websocket_push",
]


class LatencyProfiler:
    """Thread-safe per-stage latency accumulator."""

    def __init__(self) -> None:
        self._stage_times: dict[str, list[float]] = {s: [] for s in LATENCY_STAGES}
        self._dropped_frames: int = 0
        self._total_frames: int = 0
        self._start_time: float | None = None
        self._queue_wait_times: list[float] = []

    def start(self) -> None:
        self._start_time = time.monotonic()

    def record_stage(self, stage: str, duration_ms: float) -> None:
        if stage not in self._stage_times:
            self._stage_times[stage] = []
        self._stage_times[stage].append(duration_ms)

    def record_frame(self, dropped: bool = False) -> None:
        self._total_frames += 1
        if dropped:
            self._dropped_frames += 1

    def record_queue_wait(self, wait_ms: float) -> None:
        self._queue_wait_times.append(wait_ms)

    @contextmanager
    def measure(self, stage: str):
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            self.record_stage(stage, elapsed_ms)

    def compute(self) -> LatencyMetricResult:
        elapsed = time.monotonic() - self._start_time if self._start_time else 1.0
        stage_results = []

        for stage, times in self._stage_times.items():
            if not times:
                continue
            stage_results.append(LatencyStageResult(
                stage=stage,
                p50_ms=round(statistics.median(times), 2),
                p90_ms=round(_percentile(times, 90), 2),
                p95_ms=round(_percentile(times, 95), 2),
                p99_ms=round(_percentile(times, 99), 2),
                max_ms=round(max(times), 2),
                avg_ms=round(sum(times) / len(times), 2),
                samples=len(times),
            ))

        avg_fps = self._total_frames / elapsed if elapsed > 0 else None
        queue_wait_avg = (
            sum(self._queue_wait_times) / len(self._queue_wait_times)
            if self._queue_wait_times else None
        )

        return LatencyMetricResult(
            stages=stage_results,
            avg_fps=round(avg_fps, 2) if avg_fps is not None else None,
            dropped_frames=self._dropped_frames,
            queue_wait_time_avg_ms=round(queue_wait_avg, 2) if queue_wait_avg is not None else None,
            total_frames_profiled=self._total_frames,
            duration_seconds=round(elapsed, 2),
        )


def _percentile(data: list[float], pct: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = max(0, int(len(sorted_data) * pct / 100) - 1)
    return sorted_data[idx]
