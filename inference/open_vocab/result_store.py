from __future__ import annotations
import json
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any


class OpenVocabResultStore:
    """Append-only JSONL result store. Thread-safe. Bounded in-memory cache."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        persistence = self._config.get("persistence", {})
        self._storage_dir = Path(persistence.get("storage_dir", "storage/open_vocab"))
        self._retention = persistence.get("recent_retention_seconds", 3600)
        self._max_recent = persistence.get("max_recent_results", 1000)
        self._lock = threading.RLock()
        self._recent: deque = deque(maxlen=self._max_recent)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _log_file(self) -> Path:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self._storage_dir / f"open_vocab_{date_str}.jsonl"

    def _sanitize(self, d: dict) -> dict:
        """Remove absolute local paths from public output."""
        out = dict(d)
        for key in ("local_path", "upload_path", "temp_path", "image_path"):
            out.pop(key, None)
        return out

    def append_result(self, result) -> None:
        record = self._sanitize(result.to_dict() if hasattr(result, "to_dict") else result)
        with self._lock:
            try:
                with open(self._log_file(), "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except OSError:
                pass  # storage failure must not crash runtime
            self._recent.append(record)

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._recent)
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items[:limit]

    def get_result(self, scan_id: str) -> dict | None:
        with self._lock:
            for item in self._recent:
                if item.get("scan_id") == scan_id:
                    return item
        # fallback: search today's file
        try:
            with open(self._log_file(), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = json.loads(line)
                        if record.get("scan_id") == scan_id:
                            return record
        except OSError:
            pass
        return None

    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            items = [i for i in self._recent if i.get("camera_id") == camera_id]
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items[:limit]

    def list_by_incident(self, incident_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            items = [i for i in self._recent if i.get("incident_id") == incident_id]
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items[:limit]

    def cleanup(self) -> int:
        cutoff = time.time() - self._retention
        with self._lock:
            before = len(self._recent)
            fresh = deque(
                (i for i in self._recent if i.get("created_at", 0) > cutoff),
                maxlen=self._max_recent,
            )
            self._recent = fresh
            return before - len(fresh)
