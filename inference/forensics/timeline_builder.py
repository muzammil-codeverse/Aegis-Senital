from __future__ import annotations

def build_timeline(events: list[dict], track_id: str) -> list[dict]:
    chain = [e for e in events if str(track_id) in {str(t) for t in e.get('track_ids', [])}]
    return sorted(chain, key=lambda e: e.get('timestamp', 0))
