from __future__ import annotations
from inference.config_runtime import load_runtime_config

def correlate(events: list[dict]) -> dict:
    try:
        weights = load_runtime_config("escalation_rules").get("weights", {})
    except FileNotFoundError:
        weights = {}
    types = {e.get('event_type') for e in events}
    score = 0.0
    if 'WEAPON_THREAT' in types:
        score += float(weights.get("WEAPON_THREAT", 0.5))
    if 'GEOFENCE_VIOLATION' in types:
        score += float(weights.get("GEOFENCE_VIOLATION", 0.3))
    if 'pursuit_behavior' in types:
        score += float(weights.get("pursuit_behavior", 0.2))
    return {"correlation_score": min(1.0, score), "types": sorted(types)}
