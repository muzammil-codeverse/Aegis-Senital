from __future__ import annotations
import threading
import time
from collections import deque
from core.event_bus import EventType, get_event_bus
from inference.anomaly.motion_anomaly import score_motion_anomaly
from inference.config_runtime import load_runtime_config

class AnomalyEngine:
    def __init__(self) -> None:
        cfg = load_runtime_config("anomaly_rules")
        self._window = int(cfg.get("baseline_window", 120))
        self._speeds: deque[float] = deque(maxlen=self._window)
        self._live_ttl = float(cfg.get("live_ttl_seconds", 120.0))
        self._max_live = int(cfg.get("max_live_anomalies", 500))
        motion_cfg = cfg.get("motion", {})
        self._thresholds = {
            "panic_zscore": float(motion_cfg.get("panic_zscore", 3.0)),
            "erratic_zscore": float(motion_cfg.get("erratic_zscore", 2.0)),
            "acceleration_threshold": float(motion_cfg.get("acceleration_threshold", 8.0)),
            "panic_scale": float(motion_cfg.get("panic_scale", 6.0)),
            "acceleration_scale": float(motion_cfg.get("acceleration_scale", 15.0)),
            "erratic_scale": float(motion_cfg.get("erratic_scale", 5.0)),
        }
        self._live: deque[dict] = deque(maxlen=self._max_live)
        self._lock = threading.RLock()

    def evaluate_motion(
        self,
        speed: float,
        accel: float,
        track_id: int,
        *,
        camera_id: str = "default",
        frame_id: int | None = None,
        timestamp: float | None = None,
    ) -> dict | None:
        now = timestamp or time.time()
        with self._lock:
            self._cleanup_locked(now)
            mu = sum(self._speeds) / len(self._speeds) if self._speeds else speed
            var = sum((s - mu) ** 2 for s in self._speeds) / len(self._speeds) if self._speeds else 0.0
            sigma = var ** 0.5
            t, sev = score_motion_anomaly(speed, accel, mu, sigma, **self._thresholds)
            self._speeds.append(speed)
        if sev <= 0:
            return None
        anomaly = {
            "anomaly_type": t,
            "severity": round(sev, 3),
            "confidence": round(min(1.0, 0.5 + sev / 2), 3),
            "supporting_tracks": [track_id],
            "track_ids": [track_id],
            "camera_id": camera_id,
            "frame_id": frame_id,
            "timestamp": now,
        }
        with self._lock:
            self._live.append(anomaly)
        get_event_bus().publish(EventType.ANOMALY_EVENT, anomaly, source=camera_id, priority=3)
        return anomaly

    def evaluate_trajectories(
        self,
        trajectories: list[dict],
        *,
        camera_id: str,
        frame_id: int,
        timestamp: float,
    ) -> list[dict]:
        anomalies = []
        for trajectory in trajectories:
            anomaly = self.evaluate_motion(
                speed=float(trajectory.get("speed", 0.0)),
                accel=float(trajectory.get("acceleration", 0.0)),
                track_id=int(trajectory.get("track_id", 0)),
                camera_id=camera_id,
                frame_id=frame_id,
                timestamp=timestamp,
            )
            if anomaly is not None:
                anomalies.append(anomaly)
        return anomalies

    def get_live_anomalies(self) -> list[dict]:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            return list(self._live)

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_locked(time.time())

    def get_metrics(self) -> dict:
        with self._lock:
            return {
                "baseline_samples": len(self._speeds),
                "live_anomalies": len(self._live),
            }

    def _cleanup_locked(self, now: float) -> None:
        while self._live and now - float(self._live[0].get("timestamp", now)) > self._live_ttl:
            self._live.popleft()
