from __future__ import annotations
import time
from collections import deque
from inference.anomaly.motion_anomaly import score_motion_anomaly
from inference.config_runtime import load_runtime_config

class AnomalyEngine:
    def __init__(self) -> None:
        cfg = load_runtime_config("anomaly_rules")
        self._window = int(cfg.get("baseline_window", 120))
        self._speeds: deque[float] = deque(maxlen=self._window)

    def evaluate_motion(self, speed: float, accel: float, track_id: int) -> dict | None:
        mu = sum(self._speeds) / len(self._speeds) if self._speeds else speed
        var = sum((s - mu) ** 2 for s in self._speeds) / len(self._speeds) if self._speeds else 0.0
        sigma = var ** 0.5
        t, sev = score_motion_anomaly(speed, accel, mu, sigma)
        self._speeds.append(speed)
        if sev <= 0:
            return None
        return {"anomaly_type": t, "severity": round(sev, 3), "confidence": round(min(1.0, 0.5 + sev / 2), 3), "supporting_tracks": [track_id], "timestamp": time.time()}
