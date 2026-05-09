from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import time


@dataclass
class TrajectoryPoint:
    x: float
    y: float
    ts: float


@dataclass
class TrajectoryRecord:
    track_id: int
    points: deque[TrajectoryPoint]
    headings: deque[float]
    velocities: deque[float]
    accelerations: deque[float]
    last_update: float = field(default_factory=time.time)


class TrajectoryStore:
    def __init__(self, history_size: int, ttl_seconds: float) -> None:
        self._history_size = history_size
        self._ttl = ttl_seconds
        self._records: dict[int, TrajectoryRecord] = {}

    def cleanup(self, now: float | None = None) -> None:
        n = now or time.time()
        expired = [tid for tid, r in self._records.items() if n - r.last_update > self._ttl]
        for tid in expired:
            del self._records[tid]

    def get_or_create(self, track_id: int) -> TrajectoryRecord:
        rec = self._records.get(track_id)
        if rec:
            return rec
        rec = TrajectoryRecord(track_id, deque(maxlen=self._history_size), deque(maxlen=self._history_size), deque(maxlen=self._history_size), deque(maxlen=self._history_size))
        self._records[track_id] = rec
        return rec

    def get(self, track_id: int) -> TrajectoryRecord | None:
        return self._records.get(track_id)

    def items(self) -> list[tuple[int, TrajectoryRecord]]:
        return list(self._records.items())
