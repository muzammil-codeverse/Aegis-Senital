from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from core.event_bus.backends import EventBackend, InMemoryEventBackend
from core.event_bus.event_types import EventType


@dataclass
class EventRecord:
    event_type: str
    payload: Any
    source: str = "runtime"
    priority: int = 5
    metadata: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    @property
    def stream_id(self) -> str:
        return self.source

    @property
    def event(self) -> Any:
        return self.payload

    @property
    def published_at(self) -> float:
        return self.timestamp

    def to_dict(self) -> dict:
        payload = self.payload.to_dict() if hasattr(self.payload, "to_dict") else self.payload
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "payload": payload,
            "metadata": dict(self.metadata),
        }


class DistributedEventBus:
    def __init__(self, backend: EventBackend | None = None, max_recent: int = 10_000) -> None:
        self._backend = backend or InMemoryEventBackend(max_events=max_recent)

    def publish(
        self,
        event_type: EventType | str,
        payload: Any,
        *,
        source: str = "runtime",
        priority: int = 5,
        metadata: dict | None = None,
    ) -> EventRecord:
        record = EventRecord(
            event_type=event_type.value if isinstance(event_type, EventType) else str(event_type),
            payload=payload,
            source=source,
            priority=int(priority),
            metadata=metadata or {},
        )
        self._backend.publish(record)
        return record

    async def publish_async(
        self,
        event_type: EventType | str,
        payload: Any,
        *,
        source: str = "runtime",
        priority: int = 5,
        metadata: dict | None = None,
    ) -> EventRecord:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.publish(
                event_type,
                payload,
                source=source,
                priority=priority,
                metadata=metadata,
            ),
        )

    def publish_event(self, event: Any, stream_id: str = "runtime") -> EventRecord:
        event_type = getattr(event, "event_type", None)
        if event_type is None and isinstance(event, dict):
            event_type = event.get("event_type")
        priority_name = getattr(event, "priority_level", None)
        if priority_name is None and isinstance(event, dict):
            priority_name = event.get("priority_level")
        priority = _priority_value(priority_name)
        return self.publish(
            _event_type_for_payload(event_type),
            event,
            source=stream_id,
            priority=priority,
            metadata={"source_event_type": event_type},
        )

    def subscribe(self, event_type: EventType | str | None, callback: Callable[[EventRecord], None]) -> None:
        resolved = None
        if event_type is not None:
            resolved = event_type.value if isinstance(event_type, EventType) else str(event_type)
        self._backend.subscribe(resolved, callback)

    def replay_recent(self, event_type: EventType | str | None = None, limit: int = 100) -> list[EventRecord]:
        resolved = None
        if event_type is not None:
            resolved = event_type.value if isinstance(event_type, EventType) else str(event_type)
        return self._backend.replay_recent(resolved, limit)  # type: ignore[return-value]

    def consume_events(self, max_events: int = 100, timeout: float = 0.0) -> list[EventRecord]:
        if timeout > 0:
            time.sleep(min(timeout, 0.1))
        return self.replay_recent(limit=max_events)

    def dead_letter_queue(self, limit: int = 100) -> list[object]:
        return self._backend.dead_letters(limit)

    @property
    def qsize(self) -> int:
        return int(self.health().get("recent_depth", 0))

    def health(self) -> dict:
        return self._backend.health()

    def shutdown(self) -> None:
        return None


def _event_type_for_payload(source_event_type: Any) -> EventType:
    label = str(source_event_type or "").upper()
    if "ANOMALY" in label:
        return EventType.ANOMALY_EVENT
    if "INCIDENT" in label:
        return EventType.INCIDENT_EVENT
    if "ALERT" in label:
        return EventType.ALERT_EVENT
    if label:
        return EventType.THREAT_EVENT
    return EventType.SYSTEM_EVENT


def _priority_value(priority_name: Any) -> int:
    order = {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 5, "LOW": 7}
    return order.get(str(priority_name or "LOW").upper(), 7)


def _default_bus() -> DistributedEventBus:
    try:
        from inference.config_runtime import load_runtime_config
    except ImportError:
        cfg = {}
    else:
        try:
            cfg = load_runtime_config("event_bus")
        except FileNotFoundError:
            cfg = {}
    return DistributedEventBus(max_recent=int(cfg.get("max_recent_events", 10_000)))


_bus = _default_bus()


def get_event_bus() -> DistributedEventBus:
    return _bus
