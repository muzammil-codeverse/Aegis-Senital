from __future__ import annotations

def build_replay_index(events: list[dict]) -> list[dict]:
    return [{"event_id": e.get("event_id"), "timestamp": e.get("timestamp"), "camera_id": e.get("camera_id"), "track_ids": e.get("track_ids", [])} for e in events]
