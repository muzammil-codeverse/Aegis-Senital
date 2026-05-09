from __future__ import annotations

def correlate(events: list[dict]) -> dict:
    types = {e.get('event_type') for e in events}
    score = 0.0
    if 'WEAPON_THREAT' in types:
        score += 0.5
    if 'GEOFENCE_VIOLATION' in types:
        score += 0.3
    if 'pursuit_behavior' in types:
        score += 0.2
    return {"correlation_score": min(1.0, score), "types": sorted(types)}
