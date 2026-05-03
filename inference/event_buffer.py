from __future__ import annotations
from collections import deque


class EventBuffer:
    """
    Sliding window that suppresses noise by confirming events only when
    they appear in `min_consecutive` of the last `window` sampled frames.

    Weapon example: if knife is seen in frames 10, 15, 20 (3 consecutive
    sampled frames) the event is promoted to confirmed.
    """

    def __init__(self, window: int = 10, min_consecutive: int = 3):
        self._min_consecutive = min_consecutive
        self._history: deque[frozenset[str]] = deque(maxlen=window)

    def push(self, frame_events: list[dict]) -> None:
        self._history.append(frozenset(e["event_type"] for e in frame_events))

    def confirmed_events(self, frame_events: list[dict]) -> list[dict]:
        """Return events that appeared in the last min_consecutive frames."""
        if len(self._history) < self._min_consecutive:
            return []
        recent = list(self._history)[-self._min_consecutive:]
        return [
            {**e, "confirmed": True}
            for e in frame_events
            if all(e["event_type"] in frame for frame in recent)
        ]
