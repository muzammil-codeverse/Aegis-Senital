from __future__ import annotations

import threading
import time
from collections import deque


class InMemoryRateLimiter:
    def __init__(self, max_keys: int = 10_000) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, deque[float]] = {}
        self._max_keys = max(100, int(max_keys))

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        limit = max(1, int(limit))
        window_seconds = max(1, int(window_seconds))
        with self._lock:
            events = self._events.setdefault(key, deque())
            self._prune(events, now, window_seconds)
            allowed = len(events) < limit
            if allowed:
                events.append(now)
            self._enforce_bound()
            return allowed

    def record_failure(self, key: str) -> None:
        with self._lock:
            events = self._events.setdefault(key, deque())
            events.append(time.monotonic())
            self._enforce_bound()

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def cleanup(self) -> None:
        now = time.monotonic()
        with self._lock:
            empty_keys = []
            for key, events in self._events.items():
                self._prune(events, now, 3600)
                if not events:
                    empty_keys.append(key)
            for key in empty_keys:
                self._events.pop(key, None)

    @staticmethod
    def _prune(events: deque[float], now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        while events and events[0] < cutoff:
            events.popleft()

    def _enforce_bound(self) -> None:
        if len(self._events) <= self._max_keys:
            return
        for key in list(self._events.keys())[: len(self._events) - self._max_keys]:
            self._events.pop(key, None)


login_rate_limiter = InMemoryRateLimiter()
