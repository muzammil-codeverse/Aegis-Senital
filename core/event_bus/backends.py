from __future__ import annotations

import importlib.util
import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Callable

logger = logging.getLogger(__name__)


class EventBackend(ABC):
    @abstractmethod
    def publish(self, record: object) -> bool:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, event_type: str | None, callback: Callable[[object], None]) -> None:
        raise NotImplementedError

    @abstractmethod
    def replay_recent(self, event_type: str | None = None, limit: int = 100) -> list[object]:
        raise NotImplementedError

    @abstractmethod
    def dead_letters(self, limit: int = 100) -> list[object]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict:
        raise NotImplementedError


class InMemoryEventBackend(EventBackend):
    def __init__(self, max_events: int = 10_000, dead_letter_max: int = 1_000) -> None:
        self._lock = threading.RLock()
        self._recent: deque[object] = deque(maxlen=max_events)
        self._dead_letters: deque[object] = deque(maxlen=dead_letter_max)
        self._subscribers: dict[str | None, list[Callable[[object], None]]] = defaultdict(list)
        self._published = 0

    def publish(self, record: object) -> bool:
        with self._lock:
            self._recent.append(record)
            self._published += 1
            callbacks = list(self._subscribers.get(None, []))
            callbacks.extend(self._subscribers.get(getattr(record, "event_type", None), []))

        for callback in callbacks:
            try:
                callback(record)
            except Exception as exc:
                logger.warning("Event subscriber failed for %s: %s", getattr(record, "event_id", "unknown"), exc)
                with self._lock:
                    self._dead_letters.append({"record": record, "error": str(exc)})
        return True

    def subscribe(self, event_type: str | None, callback: Callable[[object], None]) -> None:
        with self._lock:
            self._subscribers[event_type].append(callback)

    def replay_recent(self, event_type: str | None = None, limit: int = 100) -> list[object]:
        with self._lock:
            records = list(self._recent)
        if event_type is not None:
            records = [record for record in records if getattr(record, "event_type", None) == event_type]
        return records[-max(0, limit):]

    def dead_letters(self, limit: int = 100) -> list[object]:
        with self._lock:
            return list(self._dead_letters)[-max(0, limit):]

    def health(self) -> dict:
        with self._lock:
            return {
                "backend": "memory",
                "published": self._published,
                "recent_depth": len(self._recent),
                "dead_letters": len(self._dead_letters),
                "subscriber_count": sum(len(items) for items in self._subscribers.values()),
            }


class RedisEventBackend(EventBackend):
    """
    Optional Redis skeleton. It is only constructible when the redis package is
    installed; callers should fall back to InMemoryEventBackend otherwise.
    """

    dependency_available = importlib.util.find_spec("redis") is not None

    def __init__(self, *args, **kwargs) -> None:
        if not self.dependency_available:
            raise RuntimeError("RedisEventBackend requires optional dependency 'redis'")
        raise NotImplementedError("Redis event backend is reserved for distributed deployment")
