from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertState(Enum):
    NEW = "new"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    SUPPRESSED = "suppressed"


_ALLOWED_TRANSITIONS: dict[AlertState, set[AlertState]] = {
    AlertState.NEW: {
        AlertState.DISPATCHED,
        AlertState.ACKNOWLEDGED,
        AlertState.ESCALATED,
        AlertState.RESOLVED,
        AlertState.EXPIRED,
        AlertState.SUPPRESSED,
    },
    AlertState.DISPATCHED: {
        AlertState.ACKNOWLEDGED,
        AlertState.ESCALATED,
        AlertState.RESOLVED,
        AlertState.EXPIRED,
        AlertState.SUPPRESSED,
    },
    AlertState.ACKNOWLEDGED: {
        AlertState.ESCALATED,
        AlertState.RESOLVED,
        AlertState.EXPIRED,
    },
    AlertState.ESCALATED: {
        AlertState.DISPATCHED,
        AlertState.ACKNOWLEDGED,
        AlertState.RESOLVED,
        AlertState.EXPIRED,
    },
    AlertState.RESOLVED: set(),
    AlertState.EXPIRED: set(),
    AlertState.SUPPRESSED: set(),
}


@dataclass
class Alert:
    incident_id: str | None
    event_ids: list[str]
    camera_ids: list[str]
    track_ids: list[int]
    identity_ids: list[str]
    severity: AlertSeverity
    state: AlertState
    title: str
    description: str
    risk_score: float
    confidence: float
    alert_id: str = field(default_factory=lambda: f"alert-{uuid.uuid4()}")
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    dispatched_at: float | None = None
    acknowledged_at: float | None = None
    resolved_at: float | None = None
    escalation_count: int = 0
    metadata: dict = field(default_factory=dict)

    def transition_to(
        self,
        state: AlertState,
        *,
        now: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AlertState, AlertState]:
        if state == self.state:
            self.updated_at = now or time.time()
            if state == AlertState.ESCALATED:
                self.escalation_count += 1
            if metadata:
                self.metadata.setdefault("transitions", []).append(
                    {"from": self.state.value, "to": state.value, "timestamp": self.updated_at, "metadata": metadata}
                )
            return self.state, state
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if state not in allowed:
            raise ValueError(f"Invalid alert transition {self.state.value} -> {state.value}")
        previous = self.state
        current_time = now or time.time()
        self.state = state
        self.updated_at = current_time
        if state == AlertState.DISPATCHED and self.dispatched_at is None:
            self.dispatched_at = current_time
        elif state == AlertState.ACKNOWLEDGED and self.acknowledged_at is None:
            self.acknowledged_at = current_time
        elif state == AlertState.RESOLVED and self.resolved_at is None:
            self.resolved_at = current_time
        elif state == AlertState.ESCALATED:
            self.escalation_count += 1
        if metadata:
            self.metadata.setdefault("transitions", []).append(
                {"from": previous.value, "to": state.value, "timestamp": current_time, "metadata": metadata}
            )
        return previous, state

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "incident_id": self.incident_id,
            "event_ids": list(self.event_ids),
            "camera_ids": list(self.camera_ids),
            "track_ids": list(self.track_ids),
            "identity_ids": list(self.identity_ids),
            "severity": self.severity.value,
            "state": self.state.value,
            "title": self.title,
            "description": self.description,
            "risk_score": float(self.risk_score),
            "confidence": float(self.confidence),
            "created_at": float(self.created_at),
            "updated_at": float(self.updated_at),
            "dispatched_at": self.dispatched_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "escalation_count": int(self.escalation_count),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Alert":
        return cls(
            alert_id=payload.get("alert_id") or f"alert-{uuid.uuid4()}",
            incident_id=payload.get("incident_id"),
            event_ids=list(payload.get("event_ids", [])),
            camera_ids=list(payload.get("camera_ids", [])),
            track_ids=[int(value) for value in payload.get("track_ids", [])],
            identity_ids=list(payload.get("identity_ids", [])),
            severity=_coerce_severity(payload.get("severity")),
            state=_coerce_state(payload.get("state")),
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            risk_score=float(payload.get("risk_score", 0.0)),
            confidence=float(payload.get("confidence", 0.0)),
            created_at=float(payload.get("created_at", time.time())),
            updated_at=float(payload.get("updated_at", time.time())),
            dispatched_at=payload.get("dispatched_at"),
            acknowledged_at=payload.get("acknowledged_at"),
            resolved_at=payload.get("resolved_at"),
            escalation_count=int(payload.get("escalation_count", 0)),
            metadata=dict(payload.get("metadata", {})),
        )


def _coerce_severity(value: Any) -> AlertSeverity:
    if isinstance(value, AlertSeverity):
        return value
    label = str(value or "info").lower()
    return AlertSeverity(label) if label in {item.value for item in AlertSeverity} else AlertSeverity.INFO


def _coerce_state(value: Any) -> AlertState:
    if isinstance(value, AlertState):
        return value
    label = str(value or "new").lower()
    return AlertState(label) if label in {item.value for item in AlertState} else AlertState.NEW
