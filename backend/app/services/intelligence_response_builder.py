from __future__ import annotations

import time
from typing import Any


class IntelligenceResponseBuilder:
    @staticmethod
    def empty(items_key: str = "items") -> dict:
        return {items_key: [], "count": 0, "status": "empty"}

    @staticmethod
    def incident_feed(incidents: list[dict]) -> dict:
        items = [
            {
                "incident_id": item.get("incident_id") or item.get("id"),
                "severity": item.get("severity", "LOW"),
                "state": item.get("state", "OPEN"),
                "camera_ids": list(item.get("camera_ids", [])),
                "track_ids": list(item.get("track_ids", [])),
                "started_at": item.get("created_at", item.get("updated_at", 0.0)),
                "updated_at": item.get("updated_at", 0.0),
                "summary": _incident_summary(item),
                "risk_score": float(item.get("risk_score", 0.0)),
                "incident_type": item.get("incident_type"),
                "event_ids": [
                    str(event.get("event_id"))
                    for event in item.get("events", [])
                    if isinstance(event, dict) and event.get("event_id")
                ],
                "metadata": dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {},
            }
            for item in incidents
        ]
        return {"items": items, "count": len(items), "status": "ok" if items else "empty"}

    @staticmethod
    def incident_detail(incident: dict | None) -> dict:
        if not incident:
            return {"item": None, "count": 0, "status": "empty"}
        return {"item": incident, "count": 1, "status": "ok"}

    @staticmethod
    def heatmap(payload: dict | None, camera_id: str) -> dict:
        if not payload:
            payload = {
                "camera_id": camera_id,
                "grid_size": [16, 9],
                "cells": [],
                "max_density": 0.0,
                "generated_at": time.time(),
            }
        payload = {
            "camera_id": payload.get("camera_id", camera_id),
            "grid_size": list(payload.get("grid_size", [16, 9])),
            "cells": list(payload.get("cells", [])),
            "max_density": float(payload.get("max_density", 0.0)),
            "generated_at": float(payload.get("generated_at", time.time())),
        }
        return {"item": payload, "count": len(payload["cells"]), "status": "ok" if payload["cells"] else "empty"}

    @staticmethod
    def timeline(track_id: int | str, events: list[dict]) -> dict:
        payload = {
            "track_id": int(track_id) if str(track_id).isdigit() else track_id,
            "events": events,
            "camera_transitions": _camera_transitions(events),
            "risk_timeline": _risk_timeline(events),
        }
        return {"item": payload, "count": len(events), "status": "ok" if events else "empty"}

    @staticmethod
    def anomalies(anomalies: list[dict]) -> dict:
        return {"items": anomalies, "count": len(anomalies), "status": "ok" if anomalies else "empty"}

    @staticmethod
    def build_alert_feed_payload(alerts: list[dict]) -> dict:
        now = time.time()
        items = [_alert_feed_item(alert, now) for alert in alerts]
        return {"items": items, "count": len(items), "status": "ok" if items else "empty"}

    @staticmethod
    def build_alert_detail_payload(alert: dict | None) -> dict:
        if alert is None:
            return {"item": None, "status": "not_found"}
        return {"item": alert, "status": "ok"}

    @staticmethod
    def build_alert_history_payload(history: list[dict]) -> dict:
        return {"items": history, "count": len(history), "status": "ok" if history else "empty"}

    @staticmethod
    def build_operator_queue_payload(alerts: list[dict]) -> dict:
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        ordered = sorted(
            alerts,
            key=lambda alert: (
                priority_order.get(str(alert.get("severity", "info")).lower(), 5),
                float(alert.get("created_at", 0.0)),
            ),
        )
        return IntelligenceResponseBuilder.build_alert_feed_payload(ordered)


def _incident_summary(item: dict) -> str:
    incident_type = item.get("incident_type", "INCIDENT")
    cameras = item.get("camera_ids", [])
    tracks = item.get("track_ids", [])
    return f"{incident_type} on {len(cameras)} camera(s), {len(tracks)} track(s)"


def _camera_transitions(events: list[dict]) -> list[dict]:
    transitions = []
    previous: dict[str, Any] | None = None
    for event in sorted(events, key=lambda item: item.get("timestamp", 0.0)):
        camera_id = event.get("camera_id")
        if camera_id is None and event.get("camera_ids"):
            camera_id = event["camera_ids"][0]
        if previous and camera_id and camera_id != previous.get("camera_id"):
            transitions.append(
                {
                    "from": previous.get("camera_id"),
                    "to": camera_id,
                    "timestamp": event.get("timestamp"),
                }
            )
        previous = {"camera_id": camera_id, "timestamp": event.get("timestamp")}
    return transitions


def _risk_timeline(events: list[dict]) -> list[dict]:
    return [
        {
            "timestamp": event.get("timestamp", 0.0),
            "risk_score": float(event.get("risk_score", event.get("metadata", {}).get("risk_score", 0.0)) or 0.0),
        }
        for event in events
    ]


def _alert_feed_item(alert: dict, now: float) -> dict:
    created_at = float(alert.get("created_at", now) or now)
    return {
        "alert_id": str(alert.get("alert_id", "")),
        "incident_id": alert.get("incident_id"),
        "event_ids": list(alert.get("event_ids", [])),
        "severity": str(alert.get("severity", "info")),
        "state": str(alert.get("state", "new")),
        "title": str(alert.get("title", "")),
        "description": str(alert.get("description", "")),
        "risk_score": float(alert.get("risk_score", 0.0) or 0.0),
        "confidence": float(alert.get("confidence", 0.0) or 0.0),
        "camera_ids": list(alert.get("camera_ids", [])),
        "track_ids": list(alert.get("track_ids", [])),
        "identity_ids": list(alert.get("identity_ids", [])),
        "created_at": created_at,
        "updated_at": float(alert.get("updated_at", created_at) or created_at),
        "age_seconds": max(0.0, round(now - created_at, 3)),
        "metadata": dict(alert.get("metadata", {})) if isinstance(alert.get("metadata"), dict) else {},
    }
