from __future__ import annotations

import threading


class SystemMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.frames_processed = 0
        self.frames_dropped = 0
        self.queue_overflows = 0
        self.avg_latency_ms = 0
        self.max_latency_ms = 0
        self.circuit_breaker_trips = 0
        self.id_switches = 0
        self.alerts_created = 0
        self.alerts_dispatched = 0
        self.alerts_acknowledged = 0
        self.alerts_resolved = 0
        self.alerts_escalated = 0
        self.alerts_suppressed = 0
        self.notification_failures = 0
        self.websocket_clients = 0
        self.websocket_dropped_messages = 0

    def increment(self, counter: str, n: int = 1):
        if n < 0:
            raise ValueError("metrics increments must be non-negative")
        with self._lock:
            setattr(self, counter, max(0, getattr(self, counter, 0) + n))

    def set_value(self, counter: str, value: int | float):
        with self._lock:
            setattr(self, counter, max(0, value))

    def to_dict(self):
        with self._lock:
            return {
                key: value
                for key, value in self.__dict__.items()
                if not key.startswith("_")
            }
