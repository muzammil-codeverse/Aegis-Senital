from __future__ import annotations

def occupancy_anomaly(current: int, baseline: float, sigma: float) -> float:
    if sigma <= 1e-6:
        return 0.0
    z = (current - baseline) / sigma
    return max(0.0, min(1.0, z / 5.0))
