from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inference.config_runtime import load_runtime_config


class TimelineStore:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _safe_config()
        self._base_dir = Path(cfg.get("timeline_dir", "storage/forensics/timelines"))
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._recent = deque(maxlen=int(cfg.get("recent_records", 5_000)))
        self._lock = threading.RLock()

    def append(self, record: dict[str, Any]) -> str:
        normalized = _normalize_record(record)
        path = self._path_for(float(normalized["timestamp"]))
        line = json.dumps(normalized, sort_keys=True)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._recent.append(normalized)
        return str(path)

    def get_track_timeline(self, track_id: int | str, limit: int = 500) -> list[dict]:
        needle = str(track_id)
        with self._lock:
            rows = [
                record for record in self._recent
                if needle in {str(value) for value in record.get("track_ids", [])}
            ]
        rows.sort(key=lambda record: record.get("timestamp", 0.0))
        return rows[-max(0, limit):]

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._recent)[-max(0, limit):]

    def _path_for(self, timestamp: float) -> Path:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return self._base_dir / dt.strftime("%Y/%m/%d/%H.jsonl")


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": float(record.get("timestamp") or time.time()),
        "camera_id": str(record.get("camera_id") or "default"),
        "frame_id": int(record.get("frame_id") or 0),
        "track_ids": list(record.get("track_ids") or []),
        "identity_ids": list(record.get("identity_ids") or []),
        "event_ids": list(record.get("event_ids") or []),
        "incident_ids": list(record.get("incident_ids") or []),
        "snapshot_path": record.get("snapshot_path"),
        # Phase 23: open-vocabulary scan references
        "open_vocab_scan_ids": list(record.get("open_vocab_scan_ids") or []),
        "open_vocab_detections": list(record.get("open_vocab_detections") or []),
        "metadata": dict(record.get("metadata") or {}),
    }


def _safe_config() -> dict:
    try:
        return load_runtime_config("forensics")
    except FileNotFoundError:
        return {}
