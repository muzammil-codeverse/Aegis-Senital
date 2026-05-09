from __future__ import annotations

import difflib
import logging
import threading
import time
from collections import deque
from typing import Any

from core.event_bus import EventType, get_event_bus
from inference.alerts.alert_models import Alert, AlertSeverity, AlertState
from inference.alerts.alert_router import AlertRouter
from inference.alerts.alert_store import AlertStore
from inference.config_runtime import load_runtime_config

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(
        self,
        *,
        config: dict | None = None,
        store: AlertStore | None = None,
        router: AlertRouter | None = None,
    ) -> None:
        cfg = config or _safe_rules()
        self._lock = threading.RLock()
        self._store = store or AlertStore()
        self._router = router or AlertRouter(cfg)
        self._alerts: dict[str, Alert] = {}
        self._max_alerts = max(1, int(cfg.get("max_alerts", 2_000)))
        self._alert_order: deque[str] = deque()
        self._dedup_window = float(cfg.get("deduplication", {}).get("duplicate_window_seconds", 20.0))
        self._similarity_threshold = float(cfg.get("deduplication", {}).get("similarity_threshold", 0.80))
        self._default_expiry = float(cfg.get("expiry", {}).get("default_expiry_seconds", 600.0))
        self._resolved_retention = float(cfg.get("expiry", {}).get("resolved_retention_seconds", 1800.0))
        self._high_unresolved = float(cfg.get("escalation", {}).get("unresolved_high_seconds", 60.0))
        self._critical_unresolved = float(cfg.get("escalation", {}).get("unresolved_critical_seconds", 30.0))
        self._max_escalations = int(cfg.get("escalation", {}).get("max_escalation_count", 3))
        self._escalation_cooldown = float(cfg.get("escalation", {}).get("cooldown_seconds", self._dedup_window))
        self._low_burst_limit = int(cfg.get("suppression", {}).get("low_priority_burst_limit", 10))
        self._burst_window = float(cfg.get("suppression", {}).get("burst_window_seconds", 30.0))
        self._dedup_keys: dict[str, tuple[str, float]] = {}
        self._last_escalation: dict[str, float] = {}
        self._low_alert_times: deque[float] = deque(maxlen=max(1, self._low_burst_limit * 2))

    def create_alert_from_incident(self, incident: Any) -> Alert | None:
        payload = _to_dict(incident)
        severity = self._router.severity_for_incident(payload)
        if severity is None:
            return None
        event_ids = [
            str(event.get("event_id"))
            for event in payload.get("events", [])
            if isinstance(event, dict) and event.get("event_id")
        ]
        alert = Alert(
            incident_id=payload.get("incident_id") or payload.get("id"),
            event_ids=event_ids,
            camera_ids=[str(value) for value in payload.get("camera_ids", [])],
            track_ids=[int(value) for value in payload.get("track_ids", [])],
            identity_ids=[str(value) for value in payload.get("identity_ids", [])],
            severity=severity,
            state=AlertState.NEW,
            title=_incident_title(payload, severity),
            description=_incident_description(payload),
            risk_score=float(payload.get("risk_score", 0.0) or 0.0),
            confidence=float(payload.get("confidence", payload.get("risk_score", 0.0)) or 0.0),
            metadata={"source": "incident", "incident": payload, "alert_type": payload.get("incident_type", "incident")},
        )
        return self._register_alert(alert)

    def create_alert_from_event(self, event: Any) -> Alert | None:
        payload = _to_dict(event)
        severity = self._router.severity_for_event(payload)
        if severity is None:
            return None
        alert = Alert(
            incident_id=None,
            event_ids=[str(payload.get("event_id"))] if payload.get("event_id") else [],
            camera_ids=[str(value) for value in payload.get("camera_ids", [])] or ([str(payload["camera_id"])] if payload.get("camera_id") else []),
            track_ids=[int(value) for value in payload.get("track_ids", [])],
            identity_ids=[str(value) for value in payload.get("identity_ids", [])],
            severity=severity,
            state=AlertState.NEW,
            title=_event_title(payload, severity),
            description=_event_description(payload),
            risk_score=float(payload.get("risk_score", payload.get("severity_score", 0.0)) or 0.0),
            confidence=float(payload.get("confidence_score", payload.get("confidence", 0.0)) or 0.0),
            metadata={"source": "event", "event": payload, "alert_type": payload.get("event_type", "event")},
        )
        return self._register_alert(alert)

    def create_watchlist_alert(self, event: Any) -> Alert | None:
        """
        Create a WATCHLIST_ALERT from a WATCHLIST_HIT event payload.

        Severity mapping mirrors the watchlist entry severity so critical
        watchlist hits produce critical alerts without going through the
        generic router.
        """
        payload = _to_dict(event)
        severity_map = {
            "critical": AlertSeverity.CRITICAL,
            "high": AlertSeverity.HIGH,
            "medium": AlertSeverity.MEDIUM,
            "low": AlertSeverity.LOW,
        }
        wl_severity = str(payload.get("severity", "medium")).lower()
        severity = severity_map.get(wl_severity, AlertSeverity.MEDIUM)

        identity_id = payload.get("identity_id")
        camera_ids = payload.get("camera_ids", [])
        if not camera_ids and payload.get("camera_id"):
            camera_ids = [str(payload["camera_id"])]
        track_ids = payload.get("track_ids", [])
        confidence = float(payload.get("confidence", 0.0) or 0.0)

        alert = Alert(
            incident_id=None,
            event_ids=[],
            camera_ids=[str(c) for c in camera_ids],
            track_ids=[int(t) for t in track_ids],
            identity_ids=[str(identity_id)] if identity_id else [],
            severity=severity,
            state=AlertState.NEW,
            title=f"{severity.value.upper()} watchlist hit: identity {str(identity_id or 'unknown')[:12]}",
            description=(
                f"Watchlisted identity detected — severity: {wl_severity}, "
                f"confidence: {confidence:.1%}, "
                f"cameras: {', '.join(str(c) for c in camera_ids) or 'unknown'}."
            ),
            risk_score=confidence,
            confidence=confidence,
            metadata={
                "source": "watchlist_hit",
                "alert_type": "watchlist_alert",
                "identity_id": identity_id,
                "watchlist_severity": wl_severity,
                "event": payload,
            },
        )
        result = self._register_alert(alert)
        if result is not None:
            try:
                _increment_metric("watchlist_alerts_created")
            except Exception:
                pass
        return result

    def acknowledge_alert(self, alert_id: str, operator_id: str | None = None) -> Alert | None:
        return self._transition(alert_id, AlertState.ACKNOWLEDGED, {"operator_id": operator_id, "action": "acknowledge"})

    def resolve_alert(self, alert_id: str, operator_id: str | None = None) -> Alert | None:
        return self._transition(alert_id, AlertState.RESOLVED, {"operator_id": operator_id, "action": "resolve"})

    def escalate_alert(self, alert_id: str, reason: str | None = None) -> Alert | None:
        now = time.time()
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            if alert.escalation_count >= self._max_escalations:
                return alert
            if now - self._last_escalation.get(alert_id, 0.0) < self._escalation_cooldown:
                return alert
            previous, current = alert.transition_to(AlertState.ESCALATED, now=now, metadata={"reason": reason})
            self._last_escalation[alert_id] = now
            escalation_recorded = previous != current or current == AlertState.ESCALATED
            if escalation_recorded:
                self._store.append_transition(alert.alert_id, previous.value, current.value, {"reason": reason})
            self._store.append_alert(alert)
        if escalation_recorded:
            _increment_metric("alerts_escalated")
        get_event_bus().publish(EventType.ALERT_EVENT, alert.to_dict(), source="alert_manager", priority=_priority(alert), metadata={"transition": "escalated"})
        return alert

    def mark_dispatched(self, alert_id: str, metadata: dict | None = None) -> Alert | None:
        return self._transition(alert_id, AlertState.DISPATCHED, metadata or {"action": "dispatch"})

    def suppress_duplicate(self, alert: Alert) -> bool:
        now = time.time()
        key = self._dedup_key(alert)
        with self._lock:
            self._prune_dedup_locked(now)
            if self._low_priority_burst_locked(alert, now):
                self._suppress_locked(alert, "low priority burst suppression")
                return True
            existing = self._dedup_keys.get(key)
            if existing and now - existing[1] <= self._dedup_window:
                self._suppress_locked(alert, "duplicate key inside window", existing_alert_id=existing[0])
                return True
            for existing_id in reversed(list(self._alert_order)):
                existing_alert = self._alerts.get(existing_id)
                if existing_alert is None or now - existing_alert.created_at > self._dedup_window:
                    continue
                if _similar(alert.title, existing_alert.title) >= self._similarity_threshold and set(alert.camera_ids) & set(existing_alert.camera_ids):
                    self._suppress_locked(alert, "similar alert inside window", existing_alert_id=existing_alert.alert_id)
                    return True
            return False

    def expire_stale_alerts(self, now: float | None = None) -> int:
        current = now or time.time()
        expired = 0
        to_remove: list[str] = []
        with self._lock:
            for alert_id, alert in list(self._alerts.items()):
                age = current - alert.updated_at
                if alert.state in {AlertState.RESOLVED, AlertState.SUPPRESSED, AlertState.EXPIRED}:
                    if age > self._resolved_retention:
                        to_remove.append(alert_id)
                    continue
                if self._should_auto_escalate(alert, current):
                    self.escalate_alert(alert.alert_id, reason="unresolved alert exceeded escalation threshold")
                    continue
                if current - alert.created_at > self._default_expiry:
                    previous, current_state = alert.transition_to(AlertState.EXPIRED, now=current, metadata={"reason": "expiry"})
                    self._store.append_transition(alert.alert_id, previous.value, current_state.value, {"reason": "expiry"})
                    self._store.append_alert(alert)
                    expired += 1
            for alert_id in to_remove:
                self._alerts.pop(alert_id, None)
            if to_remove:
                self._compact_order_locked()
        return expired

    def get_alert(self, alert_id: str) -> Alert | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def list_alerts(
        self,
        state: str | AlertState | None = None,
        severity: str | AlertSeverity | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        self.expire_stale_alerts()
        state_filter = _state_value(state)
        severity_filter = _severity_value(severity)
        with self._lock:
            alerts = [self._alerts[alert_id] for alert_id in self._alert_order if alert_id in self._alerts]
        if state_filter is not None:
            alerts = [alert for alert in alerts if alert.state.value == state_filter]
        if severity_filter is not None:
            alerts = [alert for alert in alerts if alert.severity.value == severity_filter]
        alerts.sort(key=lambda item: item.updated_at, reverse=True)
        return alerts[:max(0, limit)]

    def get_live_alert_feed(self, limit: int = 100) -> list[dict]:
        active = {
            AlertState.NEW,
            AlertState.DISPATCHED,
            AlertState.ACKNOWLEDGED,
            AlertState.ESCALATED,
        }
        return [alert.to_dict() for alert in self.list_alerts(limit=limit) if alert.state in active]

    def get_alert_history(self, alert_id: str) -> list[dict]:
        return self._store.get_alert_history(alert_id)

    def record_dispatch_attempt(self, alert_id: str, channel: str, result: dict) -> None:
        self._store.append_dispatch_attempt(alert_id, channel, result)
        if not result.get("success", False):
            _increment_metric("notification_failures")

    def _register_alert(self, alert: Alert) -> Alert | None:
        if self.suppress_duplicate(alert):
            return alert
        now = time.time()
        with self._lock:
            self._alerts[alert.alert_id] = alert
            self._alert_order.append(alert.alert_id)
            self._dedup_keys[self._dedup_key(alert)] = (alert.alert_id, now)
            if alert.severity == AlertSeverity.LOW:
                self._low_alert_times.append(now)
            self._enforce_capacity_locked()
            self._store.append_alert(alert)
        _increment_metric("alerts_created")
        get_event_bus().publish(EventType.ALERT_EVENT, alert.to_dict(), source="alert_manager", priority=_priority(alert), metadata={"state": "new"})
        return alert

    def _transition(self, alert_id: str, state: AlertState, metadata: dict | None = None) -> Alert | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            previous, current = alert.transition_to(state, metadata=metadata)
            if previous != current:
                self._store.append_transition(alert.alert_id, previous.value, current.value, metadata)
            self._store.append_alert(alert)
            if previous != current and state == AlertState.ACKNOWLEDGED:
                self._store.append_operator_action(alert.alert_id, "acknowledge", (metadata or {}).get("operator_id"))
            elif previous != current and state == AlertState.RESOLVED:
                self._store.append_operator_action(alert.alert_id, "resolve", (metadata or {}).get("operator_id"))
        metric_name = {
            AlertState.DISPATCHED: "alerts_dispatched",
            AlertState.ACKNOWLEDGED: "alerts_acknowledged",
            AlertState.RESOLVED: "alerts_resolved",
            AlertState.SUPPRESSED: "alerts_suppressed",
        }.get(state)
        if metric_name and previous != current:
            _increment_metric(metric_name)
        get_event_bus().publish(EventType.ALERT_EVENT, alert.to_dict(), source="alert_manager", priority=_priority(alert), metadata={"transition": state.value})
        return alert

    def _suppress_locked(self, alert: Alert, reason: str, existing_alert_id: str | None = None) -> None:
        alert.transition_to(
            AlertState.SUPPRESSED,
            metadata={"reason": reason, "existing_alert_id": existing_alert_id},
        )
        self._alerts[alert.alert_id] = alert
        self._alert_order.append(alert.alert_id)
        self._enforce_capacity_locked()
        self._store.append_transition(alert.alert_id, AlertState.NEW.value, AlertState.SUPPRESSED.value, {"reason": reason, "existing_alert_id": existing_alert_id})
        self._store.append_alert(alert)
        _increment_metric("alerts_suppressed")
        get_event_bus().publish(EventType.ALERT_EVENT, alert.to_dict(), source="alert_manager", priority=7, metadata={"state": "suppressed"})

    def _should_auto_escalate(self, alert: Alert, now: float) -> bool:
        if alert.state in {AlertState.RESOLVED, AlertState.EXPIRED, AlertState.SUPPRESSED}:
            return False
        if alert.escalation_count >= self._max_escalations:
            return False
        elapsed = now - alert.created_at
        if alert.severity == AlertSeverity.CRITICAL:
            return elapsed >= self._critical_unresolved
        if alert.severity == AlertSeverity.HIGH:
            return elapsed >= self._high_unresolved
        return False

    def _dedup_key(self, alert: Alert) -> str:
        if alert.incident_id:
            return f"incident:{alert.incident_id}"
        camera = ",".join(sorted(alert.camera_ids))
        track = ",".join(str(value) for value in sorted(alert.track_ids))
        alert_type = str(alert.metadata.get("alert_type", alert.title))
        return f"event:{camera}:{track}:{alert_type}"

    def _prune_dedup_locked(self, now: float) -> None:
        cutoff = now - self._dedup_window
        self._dedup_keys = {key: value for key, value in self._dedup_keys.items() if value[1] >= cutoff}
        while self._low_alert_times and self._low_alert_times[0] < now - self._burst_window:
            self._low_alert_times.popleft()

    def _low_priority_burst_locked(self, alert: Alert, now: float) -> bool:
        if alert.severity not in {AlertSeverity.LOW, AlertSeverity.INFO}:
            return False
        while self._low_alert_times and self._low_alert_times[0] < now - self._burst_window:
            self._low_alert_times.popleft()
        return len(self._low_alert_times) >= self._low_burst_limit

    def _enforce_capacity_locked(self) -> None:
        if len(self._alert_order) > self._max_alerts * 2:
            self._compact_order_locked()
        while len(self._alerts) > self._max_alerts and self._alert_order:
            expired_id = self._alert_order.popleft()
            self._alerts.pop(expired_id, None)
        if len(self._alert_order) > self._max_alerts * 2:
            self._compact_order_locked()

    def _compact_order_locked(self) -> None:
        self._alert_order = deque(alert_id for alert_id in self._alert_order if alert_id in self._alerts)


def _safe_rules() -> dict:
    try:
        return load_runtime_config("alert_rules")
    except FileNotFoundError as exc:
        logger.warning("Alert rules config unavailable; using conservative defaults: %s", exc)
        return {}


def _to_dict(item: Any) -> dict:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(f"AlertManager expected dict or to_dict model, got {type(item)!r}")


def _incident_title(incident: dict, severity: AlertSeverity) -> str:
    return f"{severity.value.upper()} incident: {incident.get('incident_type', 'incident')}"


def _incident_description(incident: dict) -> str:
    cameras = ", ".join(str(value) for value in incident.get("camera_ids", [])) or "unknown camera"
    tracks = ", ".join(str(value) for value in incident.get("track_ids", [])) or "no tracked subject"
    return f"{incident.get('incident_type', 'Incident')} detected on {cameras}; tracks={tracks}."


def _event_title(event: dict, severity: AlertSeverity) -> str:
    return f"{severity.value.upper()} event: {event.get('event_type', 'event')}"


def _event_description(event: dict) -> str:
    cameras = ", ".join(str(value) for value in event.get("camera_ids", [])) or str(event.get("camera_id", "unknown camera"))
    tracks = ", ".join(str(value) for value in event.get("track_ids", [])) or "no tracked subject"
    return f"{event.get('event_type', 'Event')} on {cameras}; tracks={tracks}."


def _similar(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _priority(alert: Alert) -> int:
    return {
        AlertSeverity.CRITICAL: 1,
        AlertSeverity.HIGH: 3,
        AlertSeverity.MEDIUM: 5,
        AlertSeverity.LOW: 7,
        AlertSeverity.INFO: 9,
    }[alert.severity]


def _state_value(state: str | AlertState | None) -> str | None:
    if state is None:
        return None
    return state.value if isinstance(state, AlertState) else str(state).lower()


def _severity_value(severity: str | AlertSeverity | None) -> str | None:
    if severity is None:
        return None
    return severity.value if isinstance(severity, AlertSeverity) else str(severity).lower()


def _increment_metric(name: str, count: int = 1) -> None:
    try:
        from inference.metrics import metrics
        metrics.increment(name, count)
    except Exception as exc:
        logger.warning("Core metric increment failed for %s: %s", name, exc)
    try:
        from inference.monitoring.metrics import get_metrics
        get_metrics().increment(name, count)
    except Exception as exc:
        logger.warning("Monitoring metric increment failed for %s: %s", name, exc)
