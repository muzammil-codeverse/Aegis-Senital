from __future__ import annotations
import time
from collections import deque
from inference.reasoning.correlation_engine import correlate
from inference.reasoning.escalation_engine import escalation_state

class IncidentEngine:
    def __init__(self, max_events: int = 2000, dedup_seconds: float = 20.0) -> None:
        self._events: deque[dict] = deque(maxlen=max_events)
        self._incidents: dict[str, dict] = {}
        self._last_by_key: dict[str, float] = {}
        self._dedup_seconds = dedup_seconds

    def ingest(self, event: dict) -> dict | None:
        key = f"{event.get('camera_id','default')}:{event.get('event_type')}"
        now = time.time()
        if now - self._last_by_key.get(key, 0.0) < self._dedup_seconds:
            return None
        self._last_by_key[key] = now
        self._events.append(event)
        corr = correlate([event])
        inc_id = event.get("event_id", f"inc-{int(now*1000)}")
        incident = {"id": inc_id, "state": escalation_state(corr['correlation_score']), "score": corr['correlation_score'], "events": [event], "updated_at": now}
        self._incidents[inc_id] = incident
        return incident

    def list_incidents(self) -> list[dict]:
        return sorted(self._incidents.values(), key=lambda x: x["updated_at"], reverse=True)
