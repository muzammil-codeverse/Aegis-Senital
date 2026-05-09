from __future__ import annotations

def snapshot(incident: dict) -> dict:
    return {"id": incident.get("id"), "state": incident.get("state"), "score": incident.get("score"), "event_count": len(incident.get("events", []))}
