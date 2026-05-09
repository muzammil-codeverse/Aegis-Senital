from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inference.config_runtime import load_runtime_config


class ReplayIndexer:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _safe_config()
        self._base_dir = Path(cfg.get("replay_index_dir", "storage/forensics/replay_index"))
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._recent = deque(maxlen=int(cfg.get("recent_records", 5_000)))
        self._lock = threading.RLock()

    def append(self, timeline_record: dict[str, Any]) -> str:
        record = {
            "timestamp": float(timeline_record.get("timestamp") or time.time()),
            "camera_id": timeline_record.get("camera_id", "default"),
            "frame_id": timeline_record.get("frame_id", 0),
            "track_ids": list(timeline_record.get("track_ids", [])),
            "identity_ids": list(timeline_record.get("identity_ids", [])),
            "event_ids": list(timeline_record.get("event_ids", [])),
            "incident_ids": list(timeline_record.get("incident_ids", [])),
            "timeline_path": timeline_record.get("metadata", {}).get("timeline_path"),
        }
        path = self._path_for(record["timestamp"])
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            self._recent.append(record)
        return str(path)

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._recent)[-max(0, limit):]

    def _path_for(self, timestamp: float) -> Path:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return self._base_dir / dt.strftime("%Y/%m/%d/%H.jsonl")


def build_replay_index(events: list[dict]) -> list[dict]:
    return [
        {
            "event_id": e.get("event_id"),
            "timestamp": e.get("timestamp"),
            "camera_id": e.get("camera_id"),
            "track_ids": e.get("track_ids", []),
        }
        for e in events
    ]


def _safe_config() -> dict:
    try:
        return load_runtime_config("forensics")
    except FileNotFoundError:
        return {}
