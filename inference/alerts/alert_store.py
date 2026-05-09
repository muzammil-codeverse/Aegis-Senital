from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inference.alerts.alert_models import Alert

logger = logging.getLogger(__name__)


class AlertStore:
    def __init__(self, base_dir: str = "storage/alerts", recent_limit: int = 5_000) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._recent: deque[dict] = deque(maxlen=recent_limit)
        self._lock = threading.RLock()

    def append_alert(self, alert: Alert) -> str:
        return self._append(
            {
                "record_type": "alert",
                "timestamp": time.time(),
                "alert_id": alert.alert_id,
                "alert": alert.to_dict(),
            }
        )

    def append_transition(
        self,
        alert_id: str,
        from_state: str,
        to_state: str,
        metadata: dict | None = None,
    ) -> str:
        return self._append(
            {
                "record_type": "transition",
                "timestamp": time.time(),
                "alert_id": alert_id,
                "from_state": from_state,
                "to_state": to_state,
                "metadata": metadata or {},
            }
        )

    def append_dispatch_attempt(self, alert_id: str, channel: str, result: dict) -> str:
        return self._append(
            {
                "record_type": "dispatch_attempt",
                "timestamp": time.time(),
                "alert_id": alert_id,
                "channel": channel,
                "result": result,
            }
        )

    def append_operator_action(
        self,
        alert_id: str,
        action: str,
        operator_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        return self._append(
            {
                "record_type": "operator_action",
                "timestamp": time.time(),
                "alert_id": alert_id,
                "action": action,
                "operator_id": operator_id,
                "metadata": metadata or {},
            }
        )

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._recent)[-max(0, limit):]

    def get_alert_history(self, alert_id: str) -> list[dict]:
        rows: list[dict] = []
        for path in sorted(self._base_dir.glob("*.jsonl")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError as exc:
                            logger.warning("Skipping corrupt alert history row in %s: %s", path, exc)
                            continue
                        if record.get("alert_id") == alert_id:
                            rows.append(record)
            except OSError as exc:
                logger.warning("Unable to read alert history file %s: %s", path, exc)
                continue
        with self._lock:
            rows.extend(record for record in self._recent if record.get("alert_id") == alert_id)
        rows = _deduplicate_records(rows)
        rows.sort(key=lambda item: item.get("timestamp", 0.0))
        return rows

    def _append(self, record: dict[str, Any]) -> str:
        path = self._path_for(float(record.get("timestamp", time.time())))
        line = json.dumps(record, sort_keys=True)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._recent.append(record)
        return str(path)

    def _path_for(self, timestamp: float) -> Path:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return self._base_dir / dt.strftime("%Y-%m-%d.jsonl")


def _deduplicate_records(records: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped
