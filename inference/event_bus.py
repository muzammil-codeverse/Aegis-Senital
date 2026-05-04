from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Phase 6: global event rate limit (events/sec); LOW priority events are
# dropped first when the rate is exceeded.
_DEFAULT_MAX_RATE: int = 1_000


@dataclass
class BusEvent:
    """An inference event coupled with its originating stream identifier."""
    stream_id: str
    event: Any
    published_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EventBus:
    """
    Thread-safe FIFO queue that collects events from all stream processors.

    Phase-6 additions:
        Durable persistence — if persist_path or db_url is provided, a
        background worker thread appends every accepted event to a JSON-lines
        file and/or a PostgreSQL events_log table.  The publish path stays
        non-blocking; the persistence write is queued and processed
        asynchronously.

        Global rate limiting — max_rate events/second are accepted.  When the
        rate is exceeded only LOW-priority events are dropped; MEDIUM / HIGH /
        CRITICAL always pass through.  Dropped events are counted in
        SystemMetrics.dropped_low_priority_events.

    publish_event() is non-blocking — events are silently dropped when
    the queue is full to prevent any stream from stalling others.

    consume_events() drains a configurable batch.  Consumers set
    timeout > 0 to block briefly on the first item, then drain
    remaining entries without delay.

    Usage:
        bus = get_event_bus()
        # producer (inside StreamProcessor)
        bus.publish_event(event, stream_id="cam_01")
        # consumer (aggregation worker or API layer)
        batch = bus.consume_events(max_events=50)
    """

    def __init__(
        self,
        maxsize: int = 10_000,
        persist_path: str | None = None,
        db_url: str | None = None,
        max_rate: int = _DEFAULT_MAX_RATE,
    ) -> None:
        self._queue: queue.Queue[BusEvent] = queue.Queue(maxsize=maxsize)
        self._persist_path = persist_path
        self._db_url = db_url
        self._max_rate = max_rate

        # Rate-limiting state
        self._rate_window: list[float] = []
        self._rate_lock = threading.Lock()

        # Durable persistence worker
        self._persist_queue: queue.Queue[BusEvent | None] = queue.Queue(maxsize=50_000)
        self._persist_thread: threading.Thread | None = None
        if persist_path or db_url:
            self._start_persist_worker()

    # ── rate limiting ─────────────────────────────────────────────────────────

    def _rate_check(self, priority: str) -> bool:
        """
        Return True if this event should be dropped due to rate limiting.

        Only LOW-priority events are ever dropped.  Holds the rate lock for
        the full check+record operation to prevent races.
        """
        if priority != "LOW":
            return False
        now = time.monotonic()
        with self._rate_lock:
            cutoff = now - 1.0
            # Prune events older than the 1-second window
            self._rate_window = [t for t in self._rate_window if t >= cutoff]
            if len(self._rate_window) >= self._max_rate:
                return True  # drop
            self._rate_window.append(now)
            return False

    # ── publish ───────────────────────────────────────────────────────────────

    def publish_event(self, event: Any, stream_id: str) -> None:
        """
        Enqueue without blocking.

        Behaviour:
            1. Rate check — drop LOW-priority event when rate limit exceeded.
            2. Queue push — silently discards if the in-memory queue is full.
            3. Persist    — if a persist backend is configured, queue the event
                            for asynchronous durable write.
        """
        priority = getattr(event, "priority_level", "LOW")

        if self._rate_check(priority):
            try:
                from inference.monitoring.metrics import get_metrics
                get_metrics().record_dropped_event()
            except Exception:
                pass
            return

        bus_event = BusEvent(stream_id=stream_id, event=event)

        try:
            self._queue.put_nowait(bus_event)
        except queue.Full:
            pass

        # Non-blocking durable write
        if self._persist_path or self._db_url:
            try:
                self._persist_queue.put_nowait(bus_event)
            except queue.Full:
                logger.warning("EventBus: persistence queue full — event not durably stored")

    # ── consume ───────────────────────────────────────────────────────────────

    def consume_events(
        self,
        max_events: int = 100,
        timeout: float = 0.05,
    ) -> list[BusEvent]:
        """
        Drain up to max_events items from the bus.

        Blocks for *timeout* seconds waiting for the first item, then
        drains remaining entries immediately without further waiting.
        Returns an empty list if the bus is idle.
        """
        results: list[BusEvent] = []
        first_timeout = timeout
        for _ in range(max_events):
            try:
                results.append(self._queue.get(block=True, timeout=first_timeout))
                first_timeout = 0.0
            except queue.Empty:
                break
        return results

    # ── durable persistence ───────────────────────────────────────────────────

    def _start_persist_worker(self) -> None:
        self._persist_thread = threading.Thread(
            target=self._persist_loop,
            name="event-bus-persist",
            daemon=True,
        )
        self._persist_thread.start()
        logger.info(
            "EventBus: persistence worker started (file=%s, db=%s)",
            self._persist_path, "yes" if self._db_url else "no",
        )

    def _persist_loop(self) -> None:
        file_handle = None
        conn = None

        if self._persist_path:
            try:
                path = Path(self._persist_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                file_handle = open(path, "a", encoding="utf-8")
                logger.info("EventBus: appending events to %s", self._persist_path)
            except Exception as exc:
                logger.error("EventBus: cannot open persist file '%s': %s", self._persist_path, exc)

        if self._db_url:
            try:
                import psycopg2
                conn = psycopg2.connect(self._db_url)
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events_log (
                        id          SERIAL PRIMARY KEY,
                        stream_id   TEXT,
                        event_type  TEXT,
                        published_at TIMESTAMPTZ,
                        payload     JSONB
                    )
                    """
                )
                conn.commit()
                logger.info("EventBus: PostgreSQL persistence ready")
            except Exception as exc:
                logger.warning("EventBus: PostgreSQL persistence unavailable: %s", exc)
                conn = None

        try:
            while True:
                try:
                    bus_event = self._persist_queue.get(timeout=1.0)
                    if bus_event is None:
                        break
                    self._write_event(bus_event, file_handle, conn)
                except queue.Empty:
                    if file_handle:
                        try:
                            file_handle.flush()
                        except Exception:
                            pass
        finally:
            if file_handle:
                try:
                    file_handle.flush()
                    file_handle.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _write_event(self, bus_event: BusEvent, file_handle: Any, conn: Any) -> None:
        event_dict: Any
        if hasattr(bus_event.event, "to_dict"):
            event_dict = bus_event.event.to_dict()
        else:
            event_dict = str(bus_event.event)

        payload = {
            "stream_id": bus_event.stream_id,
            "published_at": bus_event.published_at,
            "event": event_dict,
        }

        if file_handle is not None:
            try:
                file_handle.write(json.dumps(payload) + "\n")
            except Exception as exc:
                logger.warning("EventBus: file write failed: %s", exc)

        if conn is not None:
            try:
                event_type = (
                    event_dict.get("event_type", "unknown")
                    if isinstance(event_dict, dict)
                    else "unknown"
                )
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO events_log (stream_id, event_type, published_at, payload)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        bus_event.stream_id,
                        event_type,
                        bus_event.published_at,
                        json.dumps(event_dict),
                    ),
                )
                conn.commit()
            except Exception as exc:
                logger.warning("EventBus: DB write failed: %s", exc)
                try:
                    conn.rollback()
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Flush the persistence queue and stop the persist worker."""
        if self._persist_thread is not None and self._persist_thread.is_alive():
            self._persist_queue.put(None)
            self._persist_thread.join(timeout=10.0)

    # ── introspection ─────────────────────────────────────────────────────────

    @property
    def qsize(self) -> int:
        """Approximate number of events currently queued."""
        return self._queue.qsize()


# Process-wide singleton
_bus: EventBus = EventBus()


def get_event_bus() -> EventBus:
    """Return the process-wide EventBus singleton."""
    return _bus
