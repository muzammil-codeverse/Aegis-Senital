from __future__ import annotations

from typing import Any

from inference.forensics.timeline_store import TimelineStore


class TimelineBuilder:
    def __init__(self, store: TimelineStore | None = None) -> None:
        self._store = store or TimelineStore()

    def record_frame(
        self,
        *,
        timestamp: float,
        camera_id: str,
        frame_id: int,
        tracks: list[Any] | None = None,
        events: list[Any] | None = None,
        incidents: list[dict] | None = None,
        anomalies: list[dict] | None = None,
        snapshot_path: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        track_ids = [_get(item, "track_id") for item in tracks or []]
        identity_ids = [
            _get(item, "identity_id")
            for item in tracks or []
            if _get(item, "identity_id") is not None
        ]
        identity_ids.extend(
            identity_id
            for event in events or []
            for identity_id in (_get(event, "identity_ids") or [])
        )
        event_ids = [_get(event, "event_id") for event in events or [] if _get(event, "event_id") is not None]
        incident_ids = [
            _get(incident, "incident_id") or _get(incident, "id")
            for incident in incidents or []
            if (_get(incident, "incident_id") or _get(incident, "id")) is not None
        ]
        record = {
            "timestamp": timestamp,
            "camera_id": camera_id,
            "frame_id": frame_id,
            "track_ids": sorted({value for value in track_ids if value is not None}),
            "identity_ids": sorted({value for value in identity_ids if value is not None}),
            "event_ids": event_ids,
            "incident_ids": incident_ids,
            "snapshot_path": snapshot_path,
            "metadata": {
                **(metadata or {}),
                "anomaly_count": len(anomalies or []),
                "event_count": len(events or []),
                "incident_count": len(incidents or []),
            },
        }
        path = self._store.append(record)
        record["metadata"]["timeline_path"] = path
        return record

    def get_track_timeline(self, track_id: int | str) -> list[dict]:
        return self._store.get_track_timeline(track_id)


def build_timeline(events: list[dict], track_id: str) -> list[dict]:
    chain = [e for e in events if str(track_id) in {str(t) for t in e.get("track_ids", [])}]
    return sorted(chain, key=lambda e: e.get("timestamp", 0))


def _get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)
