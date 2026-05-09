from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Any

from core.event_bus import EventType, get_event_bus
from inference.config_runtime import load_runtime_config
from ml.runtime.device_manager import is_cuda_available


class DegradationMode(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    RECOVERING = "RECOVERING"


class RuntimeSupervisor:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _safe_config()
        self._lock = threading.RLock()
        self._mode = DegradationMode.NORMAL
        self._last_mode = DegradationMode.NORMAL
        self._updated_at = time.time()
        self._latency_window = deque(maxlen=int(cfg.get("latency_window", 100)))
        self._event_lag_window = deque(maxlen=int(cfg.get("event_lag_window", 100)))
        self._metrics: dict[str, Any] = {}
        self._threads: dict[str, float] = {}
        self._queues: dict[str, dict] = {}
        self._circuit_breakers: dict[str, str] = {}
        self._thresholds = {
            "queue_warning_ratio": float(cfg.get("queue_warning_ratio", 0.75)),
            "queue_critical_ratio": float(cfg.get("queue_critical_ratio", 0.95)),
            "latency_warning_ms": float(cfg.get("latency_warning_ms", 150.0)),
            "latency_critical_ms": float(cfg.get("latency_critical_ms", 500.0)),
            "thread_stale_seconds": float(cfg.get("thread_stale_seconds", 30.0)),
            "stream_stall_seconds": float(cfg.get("stream_stall_seconds", 10.0)),
            "event_lag_warning_seconds": float(cfg.get("event_lag_warning_seconds", 2.0)),
            "event_lag_critical_seconds": float(cfg.get("event_lag_critical_seconds", 10.0)),
        }
        self._gpu_required = bool(cfg.get("require_gpu", False))
        self._recommendations: list[str] = []

    def update_metric(self, name: str, value: Any) -> None:
        with self._lock:
            self._metrics[name] = value
            self._updated_at = time.time()

    def report_thread_health(self, thread_name: str, heartbeat_ts: float | None = None) -> None:
        with self._lock:
            self._threads[thread_name] = heartbeat_ts or time.time()

    def report_queue_health(self, queue_name: str, depth: int, maxsize: int) -> None:
        with self._lock:
            self._queues[queue_name] = {
                "depth": int(depth),
                "maxsize": int(maxsize),
                "ratio": float(depth / max(1, maxsize)),
            }

    def report_inference_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._latency_window.append(float(latency_ms))

    def report_event_lag(self, lag_seconds: float) -> None:
        with self._lock:
            self._event_lag_window.append(float(lag_seconds))

    def report_stream_stall(self, stream_id: str, last_frame_ts: float) -> None:
        with self._lock:
            self._metrics[f"stream:{stream_id}:last_frame_ts"] = float(last_frame_ts)

    def report_circuit_breaker(self, name: str, state: str) -> None:
        with self._lock:
            self._circuit_breakers[name] = state

    def evaluate_health(self) -> DegradationMode:
        now = time.time()
        recommendations: list[str] = []
        mode = DegradationMode.NORMAL

        with self._lock:
            max_queue_ratio = max((q["ratio"] for q in self._queues.values()), default=0.0)
            avg_latency = (
                sum(self._latency_window) / len(self._latency_window)
                if self._latency_window else 0.0
            )
            avg_event_lag = (
                sum(self._event_lag_window) / len(self._event_lag_window)
                if self._event_lag_window else 0.0
            )
            stale_threads = [
                name for name, ts in self._threads.items()
                if now - ts > self._thresholds["thread_stale_seconds"]
            ]
            stalled_streams = [
                key.split(":", 2)[1]
                for key, ts in self._metrics.items()
                if key.startswith("stream:") and key.endswith(":last_frame_ts")
                and now - float(ts) > self._thresholds["stream_stall_seconds"]
            ]
            open_breakers = [
                name for name, state in self._circuit_breakers.items()
                if str(state).upper() == "OPEN"
            ]

            if self._gpu_required and not is_cuda_available():
                mode = DegradationMode.CRITICAL
                recommendations.append("GPU is required by config but CUDA is unavailable")
            if max_queue_ratio >= self._thresholds["queue_critical_ratio"]:
                mode = DegradationMode.CRITICAL
                recommendations.append("Reduce ingestion rate or increase queue capacity")
            elif max_queue_ratio >= self._thresholds["queue_warning_ratio"] and mode != DegradationMode.CRITICAL:
                mode = DegradationMode.DEGRADED
                recommendations.append("Queue saturation is elevated")

            if avg_latency >= self._thresholds["latency_critical_ms"]:
                mode = DegradationMode.CRITICAL
                recommendations.append("Inference latency exceeds critical threshold")
            elif avg_latency >= self._thresholds["latency_warning_ms"] and mode == DegradationMode.NORMAL:
                mode = DegradationMode.DEGRADED
                recommendations.append("Inference latency exceeds warning threshold")

            if avg_event_lag >= self._thresholds["event_lag_critical_seconds"]:
                mode = DegradationMode.CRITICAL
                recommendations.append("Event bus lag exceeds critical threshold")
            elif avg_event_lag >= self._thresholds["event_lag_warning_seconds"] and mode == DegradationMode.NORMAL:
                mode = DegradationMode.DEGRADED
                recommendations.append("Event bus lag is elevated")

            if stale_threads:
                mode = DegradationMode.CRITICAL
                recommendations.append(f"Stale thread heartbeat: {', '.join(sorted(stale_threads))}")
            if stalled_streams and mode == DegradationMode.NORMAL:
                mode = DegradationMode.DEGRADED
                recommendations.append(f"Stream stall detected: {', '.join(sorted(stalled_streams))}")
            if open_breakers and mode == DegradationMode.NORMAL:
                mode = DegradationMode.DEGRADED
                recommendations.append(f"Circuit breaker open: {', '.join(sorted(open_breakers))}")

            if self._last_mode in {DegradationMode.DEGRADED, DegradationMode.CRITICAL} and mode == DegradationMode.NORMAL:
                mode = DegradationMode.RECOVERING
                recommendations.append("Runtime has returned inside thresholds")

            self._mode = mode
            self._recommendations = recommendations
            self._updated_at = now
            changed = mode != self._last_mode
            self._last_mode = mode

        if changed:
            get_event_bus().publish(
                EventType.SYSTEM_EVENT,
                self.get_health_snapshot(),
                source="runtime_supervisor",
                priority=1 if mode == DegradationMode.CRITICAL else 3,
            )
        return mode

    def get_health_snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode.value,
                "updated_at": self._updated_at,
                "gpu_available": is_cuda_available(),
                "gpu_required": self._gpu_required,
                "metrics": dict(self._metrics),
                "queues": dict(self._queues),
                "threads": dict(self._threads),
                "circuit_breakers": dict(self._circuit_breakers),
                "avg_inference_latency_ms": round(
                    sum(self._latency_window) / len(self._latency_window), 3
                ) if self._latency_window else 0.0,
                "avg_event_lag_seconds": round(
                    sum(self._event_lag_window) / len(self._event_lag_window), 3
                ) if self._event_lag_window else 0.0,
                "recommendations": list(self._recommendations),
            }


def _safe_config() -> dict:
    try:
        return load_runtime_config("runtime_health")
    except FileNotFoundError:
        return {}


_supervisor: RuntimeSupervisor | None = None
_supervisor_lock = threading.Lock()


def get_runtime_supervisor() -> RuntimeSupervisor:
    global _supervisor
    if _supervisor is None:
        with _supervisor_lock:
            if _supervisor is None:
                _supervisor = RuntimeSupervisor()
    return _supervisor
