from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from enum import Enum
from typing import Any

from core.event_bus import EventType, get_event_bus
from inference.config_runtime import load_runtime_config


class IncidentState(Enum):
    OPEN = "OPEN"
    ESCALATED = "ESCALATED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class IncidentEngine:
    def __init__(self, max_events: int | None = None, dedup_seconds: float | None = None) -> None:
        cfg = _safe_config()
        suppression = cfg.get("suppression", {})
        self._max_events = int(max_events or cfg.get("max_events", 2_000))
        self._max_incidents = int(cfg.get("max_incidents", 1_000))
        self._dedup_seconds = float(dedup_seconds or suppression.get("duplicate_window_seconds", 15.0))
        self._incident_expiry_seconds = float(suppression.get("incident_expiry_seconds", 300.0))
        self._escalation_cooldown_seconds = float(suppression.get("escalation_cooldown_seconds", 20.0))
        self._decay_per_second = float(cfg.get("risk_decay_per_second", 0.001))
        self._resolve_below = float(cfg.get("resolve_below_risk", 0.10))
        self._anomaly_incident_threshold = float(cfg.get("anomaly_incident_threshold", 0.65))
        self._events: deque[dict] = deque(maxlen=self._max_events)
        self._incidents: dict[str, dict] = {}
        self._incident_order: deque[str] = deque(maxlen=self._max_incidents)
        self._last_by_key: dict[str, float] = {}
        self._last_escalation: dict[str, float] = {}
        self._lock = threading.RLock()

    def ingest(self, event: Any) -> dict | None:
        incidents = self.process(events=[event], anomalies=[], timeline_ref=None)
        return incidents[0] if incidents else None

    def process(
        self,
        *,
        events: list[Any],
        anomalies: list[dict] | None = None,
        timeline_ref: dict | None = None,
    ) -> list[dict]:
        now = time.time()
        produced: list[dict] = []
        normalized_events = [_event_to_dict(event) for event in events]
        normalized_events.extend(self._anomaly_events(anomalies or []))

        with self._lock:
            self._cleanup_locked(now)
            for event in normalized_events:
                if self._is_duplicate_locked(event, now):
                    continue
                self._events.append(event)
                incident = self._merge_event_locked(event, now, timeline_ref)
                if incident is not None:
                    produced.append(dict(incident))

        for incident in produced:
            get_event_bus().publish(
                EventType.INCIDENT_EVENT,
                incident,
                source="incident_engine",
                priority=_incident_priority(incident),
            )
        return produced

    def acknowledge(self, incident_id: str) -> bool:
        return self._set_state(incident_id, IncidentState.ACKNOWLEDGED)

    def resolve(self, incident_id: str) -> bool:
        return self._set_state(incident_id, IncidentState.RESOLVED)

    def get_incidents(self, include_expired: bool = False) -> list[dict]:
        with self._lock:
            self._cleanup_locked(time.time())
            incidents = list(self._incidents.values())
        if not include_expired:
            incidents = [item for item in incidents if item.get("state") != IncidentState.EXPIRED.value]
        return sorted(incidents, key=lambda item: item["updated_at"], reverse=True)

    def list_incidents(self) -> list[dict]:
        return self.get_incidents()

    def get_incident(self, incident_id: str) -> dict | None:
        with self._lock:
            incident = self._incidents.get(incident_id)
            return dict(incident) if incident is not None else None

    def attach_timeline_ref(self, incident_ids: list[str], timeline_ref: dict) -> None:
        ref = {
            "camera_id": timeline_ref.get("camera_id"),
            "frame_id": timeline_ref.get("frame_id"),
            "timestamp": timeline_ref.get("timestamp"),
            "path": timeline_ref.get("metadata", {}).get("timeline_path"),
        }
        with self._lock:
            for incident_id in incident_ids:
                incident = self._incidents.get(incident_id)
                if incident is not None and ref not in incident["timeline_refs"]:
                    incident["timeline_refs"].append(ref)

    def cleanup(self) -> None:
        with self._lock:
            self._cleanup_locked(time.time())

    def get_metrics(self) -> dict:
        with self._lock:
            return {
                "incident_count": len(self._incidents),
                "event_memory": len(self._events),
                "dedup_keys": len(self._last_by_key),
            }

    def _merge_event_locked(self, event: dict, now: float, timeline_ref: dict | None) -> dict:
        related_id = self._find_related_incident_locked(event, now)
        if related_id is None:
            incident = self._new_incident(event, now)
            self._incidents[incident["incident_id"]] = incident
            self._incident_order.append(incident["incident_id"])
        else:
            incident = self._incidents[related_id]
            self._update_incident(incident, event, now)

        if timeline_ref:
            ref = {
                "camera_id": timeline_ref.get("camera_id"),
                "frame_id": timeline_ref.get("frame_id"),
                "timestamp": timeline_ref.get("timestamp"),
                "path": timeline_ref.get("metadata", {}).get("timeline_path"),
            }
            if ref not in incident["timeline_refs"]:
                incident["timeline_refs"].append(ref)
        incident["id"] = incident["incident_id"]
        return incident

    def _new_incident(self, event: dict, now: float) -> dict:
        risk = _event_risk(event)
        severity = _severity(risk)
        incident_id = f"inc-{uuid.uuid4()}"
        return {
            "incident_id": incident_id,
            "id": incident_id,
            "incident_type": event.get("event_type", "UNKNOWN"),
            "severity": severity,
            "state": IncidentState.OPEN.value,
            "created_at": now,
            "updated_at": now,
            "camera_ids": sorted(_camera_ids(event)),
            "track_ids": sorted(_track_ids(event)),
            "identity_ids": sorted(_identity_ids(event)),
            "events": [event],
            "anomalies": [event] if str(event.get("event_type", "")).startswith("ANOMALY_") else [],
            "risk_score": risk,
            "confidence": float(event.get("confidence_score", event.get("confidence", risk)) or risk),
            "timeline_refs": [],
            "last_support_at": now,
        }

    def _update_incident(self, incident: dict, event: dict, now: float) -> None:
        existing_ids = {item.get("event_id") for item in incident["events"]}
        event_id = event.get("event_id")
        if event_id is None or event_id not in existing_ids:
            incident["events"].append(event)
            overflow = len(incident["events"]) - self._max_events
            if overflow > 0:
                del incident["events"][:overflow]
        if str(event.get("event_type", "")).startswith("ANOMALY_"):
            incident["anomalies"].append(event)
        incident["camera_ids"] = sorted(set(incident["camera_ids"]) | _camera_ids(event))
        incident["track_ids"] = sorted(set(incident["track_ids"]) | _track_ids(event))
        incident["identity_ids"] = sorted(set(incident["identity_ids"]) | _identity_ids(event))
        risk = max(float(incident["risk_score"]), _event_risk(event))
        if risk > float(incident["risk_score"]) and now - self._last_escalation.get(incident["incident_id"], 0.0) >= self._escalation_cooldown_seconds:
            incident["state"] = IncidentState.ESCALATED.value
            self._last_escalation[incident["incident_id"]] = now
        incident["risk_score"] = round(risk, 4)
        incident["severity"] = _severity(risk)
        incident["confidence"] = max(
            float(incident["confidence"]),
            float(event.get("confidence_score", event.get("confidence", risk)) or risk),
        )
        incident["updated_at"] = now
        incident["last_support_at"] = now

    def _find_related_incident_locked(self, event: dict, now: float) -> str | None:
        event_cameras = _camera_ids(event)
        event_tracks = _track_ids(event)
        event_identities = _identity_ids(event)
        event_type = event.get("event_type")
        for incident_id in reversed(list(self._incident_order)):
            incident = self._incidents.get(incident_id)
            if incident is None or incident.get("state") in {IncidentState.RESOLVED.value, IncidentState.EXPIRED.value}:
                continue
            if now - float(incident.get("updated_at", now)) > self._incident_expiry_seconds:
                continue
            if event_identities and event_identities & set(incident.get("identity_ids", [])):
                return incident_id
            if event_tracks and event_tracks & set(incident.get("track_ids", [])) and event_cameras & set(incident.get("camera_ids", [])):
                return incident_id
            if event_type == incident.get("incident_type") and event_cameras & set(incident.get("camera_ids", [])):
                return incident_id
        return None

    def _is_duplicate_locked(self, event: dict, now: float) -> bool:
        key = _dedup_key(event)
        previous = self._last_by_key.get(key, 0.0)
        if now - previous < self._dedup_seconds:
            return True
        self._last_by_key[key] = now
        return False

    def _cleanup_locked(self, now: float) -> None:
        for incident in self._incidents.values():
            age = now - float(incident.get("updated_at", now))
            if age >= self._incident_expiry_seconds:
                incident["state"] = IncidentState.EXPIRED.value
                incident["updated_at"] = now
                continue
            unsupported_for = now - float(incident.get("last_support_at", now))
            if unsupported_for > self._dedup_seconds and incident["state"] not in {
                IncidentState.ACKNOWLEDGED.value,
                IncidentState.RESOLVED.value,
                IncidentState.EXPIRED.value,
            }:
                decayed = max(0.0, float(incident["risk_score"]) - unsupported_for * self._decay_per_second)
                incident["risk_score"] = round(decayed, 4)
                incident["severity"] = _severity(decayed)
                if decayed <= self._resolve_below:
                    incident["state"] = IncidentState.RESOLVED.value
                    incident["updated_at"] = now

        while len(self._incident_order) > self._max_incidents:
            old_id = self._incident_order.popleft()
            self._incidents.pop(old_id, None)

        cutoff = now - self._incident_expiry_seconds
        self._last_by_key = {key: ts for key, ts in self._last_by_key.items() if ts >= cutoff}

    def _set_state(self, incident_id: str, state: IncidentState) -> bool:
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                return False
            incident["state"] = state.value
            incident["updated_at"] = time.time()
            return True

    def _anomaly_events(self, anomalies: list[dict]) -> list[dict]:
        events = []
        for anomaly in anomalies:
            risk = float(anomaly.get("severity", 0.0))
            if risk < self._anomaly_incident_threshold:
                continue
            events.append(
                {
                    "event_id": anomaly.get("anomaly_id") or f"anom-{uuid.uuid4()}",
                    "event_type": f"ANOMALY_{anomaly.get('anomaly_type', 'UNKNOWN')}",
                    "severity": _severity(risk),
                    "risk_score": risk,
                    "confidence_score": anomaly.get("confidence", risk),
                    "track_ids": anomaly.get("track_ids") or anomaly.get("supporting_tracks") or [],
                    "identity_ids": anomaly.get("identity_ids", []),
                    "camera_ids": [anomaly.get("camera_id", "default")],
                    "timestamp": anomaly.get("timestamp", time.time()),
                    "metadata": {"anomaly": anomaly},
                }
            )
        return events


def _event_to_dict(event: Any) -> dict:
    if hasattr(event, "to_dict"):
        return event.to_dict()
    if isinstance(event, dict):
        payload = event.get("metadata", {}).get("payload")
        if isinstance(payload, dict) and "event_type" in payload:
            return payload
        return dict(event)
    raise TypeError(f"IncidentEngine expected event dict or to_dict object, got {type(event)!r}")


def _event_risk(event: dict) -> float:
    return round(float(event.get("risk_score", event.get("severity_score", event.get("confidence_score", 0.0))) or 0.0), 4)


def _severity(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


def _track_ids(event: dict) -> set[int]:
    return {int(value) for value in event.get("track_ids", []) if value is not None}


def _identity_ids(event: dict) -> set[str]:
    return {str(value) for value in event.get("identity_ids", []) if value}


def _camera_ids(event: dict) -> set[str]:
    cameras = event.get("camera_ids")
    if cameras:
        return {str(value) for value in cameras}
    camera = event.get("camera_id")
    return {str(camera)} if camera else set()


def _dedup_key(event: dict) -> str:
    event_id = event.get("event_id")
    if event_id:
        return f"id:{event_id}"
    cameras = ",".join(sorted(_camera_ids(event)))
    tracks = ",".join(str(value) for value in sorted(_track_ids(event)))
    return f"{event.get('event_type')}:{cameras}:{tracks}"


def _incident_priority(incident: dict) -> int:
    return {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 5, "LOW": 7}.get(str(incident.get("severity", "LOW")).upper(), 7)


def _safe_config() -> dict:
    try:
        return load_runtime_config("incident_rules")
    except FileNotFoundError:
        return {}
