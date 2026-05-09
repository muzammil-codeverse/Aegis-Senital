from __future__ import annotations

import logging

from inference.alerts.alert_models import Alert, AlertSeverity
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)


class AlertRouter:
    def __init__(self, config: dict | None = None) -> None:
        self._config = config or _safe_rules()
        self._routing = self._config.get("routing", {})
        self._thresholds = self._config.get("severity_thresholds", {})
        self._event_rules = self._config.get("event_rules", {})

    def channels_for_alert(self, alert: Alert) -> list[str]:
        severity = alert.severity.value
        payload = self._routing.get(severity, {})
        channels = payload.get("channels", ["websocket"])
        return [str(channel) for channel in channels]

    def severity_for_incident(self, incident: dict) -> AlertSeverity | None:
        risk = float(incident.get("risk_score", 0.0) or 0.0)
        severity = str(incident.get("severity", "")).upper()
        incident_type = str(incident.get("incident_type", "")).upper()
        if incident_type == "NORMAL" or severity == "NORMAL":
            return None
        if severity == "CRITICAL" or risk >= self._risk_threshold("critical_risk_score"):
            return AlertSeverity.CRITICAL
        if severity in {"HIGH", "HIGH_RISK"} or risk >= self._risk_threshold("high_risk_score"):
            return AlertSeverity.HIGH
        if severity in {"MEDIUM", "ELEVATED"} or risk >= self._risk_threshold("medium_risk_score"):
            return AlertSeverity.MEDIUM
        if severity in {"LOW", "LOW_RISK"} or risk >= self._risk_threshold("low_risk_score"):
            return AlertSeverity.LOW
        return None

    def severity_for_event(self, event: dict) -> AlertSeverity | None:
        event_type = str(event.get("event_type", "")).upper()
        risk = float(event.get("risk_score", event.get("severity_score", 0.0)) or 0.0)
        metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), dict) else {}
        if event_type == "WEAPON_THREAT":
            rule = self._event_rules.get("weapon_threat", {})
            return _severity_from_label(rule.get("severity"), AlertSeverity.HIGH)
        if event_type == "GEOFENCE_VIOLATION":
            rule = self._event_rules.get("geofence_violation", {})
            zone_priority = str(metadata.get("zone_priority", metadata.get("priority", ""))).lower()
            critical_priorities = {str(value).lower() for value in rule.get("critical_zone_priorities", ["critical"])}
            critical_risk = float(rule.get("critical_risk_score", self._risk_threshold("critical_risk_score")))
            return AlertSeverity.CRITICAL if zone_priority in critical_priorities or risk >= critical_risk else AlertSeverity.HIGH
        if event_type == "LOITERING_DETECTED":
            rule = self._event_rules.get("loitering", {})
            repeat_count = int(metadata.get("repeat_count", 1) or 1)
            repeated_count = int(rule.get("repeated_count", 3))
            if repeat_count >= repeated_count:
                return _severity_from_label(rule.get("repeated_severity"), AlertSeverity.HIGH)
            return _severity_from_label(rule.get("default_severity"), AlertSeverity.MEDIUM)
        if event_type == "UNATTENDED_OBJECT":
            rule = self._event_rules.get("unattended_object", {})
            duration = float(metadata.get("duration_seconds", metadata.get("persistence_seconds", 0.0)) or 0.0)
            if duration < float(rule.get("min_persistence_seconds", 0.0)):
                return None
            return _severity_from_label(rule.get("default_severity"), AlertSeverity.HIGH)
        if risk >= self._risk_threshold("critical_risk_score"):
            return AlertSeverity.CRITICAL
        if risk >= self._risk_threshold("high_risk_score"):
            return AlertSeverity.HIGH
        if risk >= self._risk_threshold("medium_risk_score"):
            return AlertSeverity.MEDIUM
        return None

    def _risk_threshold(self, key: str) -> float:
        defaults = {
            "critical_risk_score": 0.80,
            "high_risk_score": 0.60,
            "medium_risk_score": 0.40,
            "low_risk_score": 0.20,
        }
        return float(self._thresholds.get(key, defaults[key]))


def _safe_rules() -> dict:
    try:
        return load_runtime_config("alert_rules")
    except FileNotFoundError as exc:
        logger.warning("Alert rules config unavailable; using conservative defaults: %s", exc)
        return {}


def _severity_from_label(value: object, fallback: AlertSeverity) -> AlertSeverity:
    label = str(value or fallback.value).lower()
    for severity in AlertSeverity:
        if severity.value == label:
            return severity
    return fallback
