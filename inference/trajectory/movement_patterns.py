from __future__ import annotations
import numpy as np


def detect_behavior(headings: list[float], velocities: list[float], accelerations: list[float]) -> dict:
    if not headings:
        return {"label": "unknown", "score": 0.0}
    h = np.array(headings)
    v = np.array(velocities) if velocities else np.array([0.0])
    a = np.array(accelerations) if accelerations else np.array([0.0])
    changes = np.abs(np.diff(h)).mean() if h.size > 1 else 0.0
    speed_var = float(v.var())
    accel_peak = float(np.max(np.abs(a)))
    if changes > 1.5 and accel_peak > 5.0:
        return {"label": "escape_behavior", "score": round(min(1.0, changes / 3.14), 3)}
    if changes > 1.2:
        return {"label": "abrupt_direction_change", "score": round(min(1.0, changes / 3.14), 3)}
    if speed_var < 0.5 and v.mean() < 1.0:
        return {"label": "stationary_clustering", "score": 0.8}
    if speed_var < 1.0 and v.mean() > 1.5:
        return {"label": "pacing", "score": 0.65}
    return {"label": "normal_motion", "score": 0.4}
