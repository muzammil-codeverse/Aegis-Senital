from __future__ import annotations

def crowd_spike_score(delta: float, threshold: float) -> float:
    if delta <= threshold:
        return 0.0
    return min(1.0, (delta - threshold) / max(1e-6, threshold))
