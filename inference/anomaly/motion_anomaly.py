from __future__ import annotations

def score_motion_anomaly(speed: float, accel: float, speed_mu: float, speed_sigma: float) -> tuple[str, float]:
    z = 0.0 if speed_sigma <= 1e-6 else (speed - speed_mu) / speed_sigma
    if z > 3.0 or accel > 8.0:
        return ("panic_motion", min(1.0, max(z / 6.0, accel / 15.0)))
    if z > 2.0:
        return ("erratic_acceleration", min(1.0, z / 5.0))
    return ("normal", 0.0)
