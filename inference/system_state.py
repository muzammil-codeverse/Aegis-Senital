from __future__ import annotations
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_FPS_WINDOW = 30          # rolling frame timestamps for FPS estimation
_LATENCY_WINDOW = 30      # rolling latency samples per module


@dataclass
class SystemState:
    """
    Full runtime observability state for the Aegis Sentinel inference pipeline.

    Legacy fields (total_frames_processed … model_status) are preserved
    for backwards compatibility.  Phase-10 additions extend the picture with
    per-module latency, scene density, and an aggregate health score.

    Fields
    ------
    total_frames_processed   cumulative frame count since startup
    active_tracks_count      live track count at last tracker.update()
    active_events            Event objects / dicts from last evaluate()
    active_events_count      len(active_events)
    last_event_time          ISO-8601 UTC of the most recent non-empty evaluate()
    fps_estimate             rolling FPS (alias for fps_actual, legacy compat)
    fps_actual               rolling FPS derived from frame timestamps
    inference_latency_ms     {"module": latest_ms} — last recorded latency
    scene_density_score      normalised scene busyness 0–1 (from EventBuffer)
    model_status             {"model": "loaded|error:…"} — legacy compat
    model_health_status      same as model_status, explicit health perspective
    system_health_score      aggregate 0–1 score (1.0 = fully healthy)
    """
    total_frames_processed: int   = 0
    active_tracks_count: int      = 0
    active_events: list           = field(default_factory=list)
    active_events_count: int      = 0
    last_event_time: str | None   = None
    fps_estimate: float           = 0.0    # legacy alias for fps_actual
    fps_actual: float             = 0.0
    inference_latency_ms: dict    = field(default_factory=dict)
    scene_density_score: float    = 0.0
    model_status: dict            = field(default_factory=dict)
    model_health_status: dict     = field(default_factory=dict)
    system_health_score: float    = 1.0


# ── Module-level singleton ─────────────────────────────────────────────────────

_state = SystemState()
_lock  = threading.Lock()
_fps_timestamps: deque[float] = deque(maxlen=_FPS_WINDOW)
_latency_history: dict[str, deque] = {}   # module → deque[float]


# ── Write interface ────────────────────────────────────────────────────────────

def update_state(
    *,
    frames_delta: int = 0,
    active_tracks: int | None = None,
    new_events: list | None = None,
    model_status: dict | None = None,
    latency_ms: dict | None = None,
    scene_density: float | None = None,
    model_health: dict | None = None,
) -> None:
    """
    Thread-safe incremental update of the global SystemState.

    Parameters
    ----------
    frames_delta    Number of frames processed since the last call.
                    Updates the rolling FPS estimator.
    active_tracks   Replace active_tracks_count with this value.
    new_events      Replace active_events list (and count) with this value.
                    Sets last_event_time when the list is non-empty.
    model_status    Merged into model_status and model_health_status.
    latency_ms      {"module": ms} — merged into inference_latency_ms and
                    the per-module rolling history used by health scoring.
    scene_density   Replace scene_density_score.
    model_health    Merged into model_health_status (explicit health dict,
                    separate from model_status if callers want both).
    """
    global _state
    with _lock:
        if frames_delta > 0:
            _state.total_frames_processed += frames_delta
            now = time.monotonic()
            _fps_timestamps.append(now)
            if len(_fps_timestamps) >= 2:
                elapsed = _fps_timestamps[-1] - _fps_timestamps[0]
                fps = round((len(_fps_timestamps) - 1) / elapsed if elapsed > 0 else 0.0, 1)
                _state.fps_actual  = fps
                _state.fps_estimate = fps  # keep legacy alias in sync

        if active_tracks is not None:
            _state.active_tracks_count = active_tracks

        if new_events is not None:
            _state.active_events       = list(new_events)
            _state.active_events_count = len(new_events)
            if new_events:
                _state.last_event_time = datetime.now(timezone.utc).isoformat()

        if model_status is not None:
            _state.model_status.update(model_status)
            _state.model_health_status.update(model_status)

        if model_health is not None:
            _state.model_health_status.update(model_health)

        if latency_ms is not None:
            _state.inference_latency_ms.update(latency_ms)
            for module, ms in latency_ms.items():
                if module not in _latency_history:
                    _latency_history[module] = deque(maxlen=_LATENCY_WINDOW)
                _latency_history[module].append(float(ms))

        if scene_density is not None:
            _state.scene_density_score = scene_density

        _state.system_health_score = _compute_health()


def record_latency(module: str, start_monotonic: float) -> float:
    """
    Convenience helper: compute elapsed ms since start_monotonic and
    record it for the named module.  Returns the elapsed value in ms.

    Typical usage inside the inference loop:
        t0 = time.monotonic()
        packet = engine.predict(frame)
        record_latency("detection_engine", t0)
    """
    elapsed_ms = round((time.monotonic() - start_monotonic) * 1000.0, 2)
    update_state(latency_ms={module: elapsed_ms})
    return elapsed_ms


# ── Read interface ─────────────────────────────────────────────────────────────

def get_system_snapshot() -> dict:
    """
    Return a full runtime analytics snapshot as a plain dict.

    Thread-safe.  Safe to call from any thread or background process.
    """
    with _lock:
        snapshot = {
            "timestamp":               datetime.now(timezone.utc).isoformat(),
            "total_frames_processed":  _state.total_frames_processed,
            "active_tracks_count":     _state.active_tracks_count,
            "active_events_count":     _state.active_events_count,
            "active_events": [
                e.to_dict() if hasattr(e, "to_dict") else e
                for e in _state.active_events
            ],
            "last_event_time":         _state.last_event_time,
            "fps_estimate":            _state.fps_estimate,
            "fps_actual":              _state.fps_actual,
            "inference_latency_ms":    dict(_state.inference_latency_ms),
            "scene_density_score":     _state.scene_density_score,
            "model_status":            dict(_state.model_status),
            "model_health_status":     dict(_state.model_health_status),
            "system_health_score":     _state.system_health_score,
        }

    logger.debug(json.dumps({"event": "system_snapshot", **snapshot}))
    return snapshot


def reset_state() -> None:
    """Reset all state and history to defaults (useful for test isolation)."""
    global _state
    with _lock:
        _fps_timestamps.clear()
        _latency_history.clear()
        _state = SystemState()


# ── Internal health computation ────────────────────────────────────────────────

def _compute_health() -> float:
    """
    Aggregate system health score ∈ [0, 1].

    Three sub-scores (must be called within the lock):
      model_health    1.0 unless any model_health_status value contains "error"
      latency_health  penalised when any module's rolling-average latency
                      exceeds 15 ms (performance requirement from spec §4)
      fps_health      penalised when fps_actual < 5 (system is stalling)
                      0.0 fps is treated as "not started yet" → 1.0 (no penalty)
    """
    # Model health
    model_errors = sum(
        1 for v in _state.model_health_status.values()
        if isinstance(v, str) and "error" in v.lower()
    )
    model_health = max(0.0, 1.0 - model_errors * 0.35)

    # Latency health: target <15 ms per module (spec §4)
    latency_penalties: list[float] = []
    for history in _latency_history.values():
        if history:
            avg_ms = sum(history) / len(history)
            # Graceful degradation: 0 penalty at ≤15 ms, full penalty at 65 ms
            penalty = max(0.0, min(1.0, (avg_ms - 15.0) / 50.0))
            latency_penalties.append(1.0 - penalty)
    latency_health = (
        sum(latency_penalties) / len(latency_penalties) if latency_penalties else 1.0
    )

    # FPS health
    fps = _state.fps_actual
    fps_health = min(1.0, fps / 15.0) if fps > 0.0 else 1.0

    return round(model_health * 0.40 + latency_health * 0.35 + fps_health * 0.25, 3)
