from __future__ import annotations


def score_motion_anomaly(
    speed: float,
    accel: float,
    speed_mu: float,
    speed_sigma: float,
    *,
    panic_zscore: float = 3.0,
    erratic_zscore: float = 2.0,
    acceleration_threshold: float = 8.0,
    panic_scale: float = 6.0,
    acceleration_scale: float = 15.0,
    erratic_scale: float = 5.0,
) -> tuple[str, float]:
    z = 0.0 if speed_sigma <= 1e-6 else (speed - speed_mu) / speed_sigma
    if z > panic_zscore or accel > acceleration_threshold:
        return ("panic_motion", min(1.0, max(z / panic_scale, accel / acceleration_scale)))
    if z > erratic_zscore:
        return ("erratic_acceleration", min(1.0, z / erratic_scale))
    return ("normal", 0.0)
