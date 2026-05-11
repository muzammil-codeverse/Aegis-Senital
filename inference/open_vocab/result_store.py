from __future__ import annotations
import time
from collections import deque
from typing import Any

from app.repositories.open_vocab_repository import (
    OpenVocabResultRepository,
    build_open_vocab_result_repository,
)


class OpenVocabResultStore:
    """Append-only JSONL result store. Thread-safe. Bounded in-memory cache."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}
        persistence = self._config.get("persistence", {})
        self._retention = persistence.get("recent_retention_seconds", 3600)
        self._max_recent = persistence.get("max_recent_results", 1000)
        self._recent: deque = deque(maxlen=self._max_recent)
        self._repository: OpenVocabResultRepository = build_open_vocab_result_repository(
            str(persistence.get("storage_dir", "storage/open_vocab"))
        )

    def _sanitize(self, d: dict) -> dict:
        """Remove absolute local paths from public output."""
        out = dict(d)
        for key in ("local_path", "upload_path", "temp_path", "image_path"):
            out.pop(key, None)
        return out

    def append_result(self, result) -> None:
        record = self._sanitize(result.to_dict() if hasattr(result, "to_dict") else result)
        try:
            self._repository.append_result(record)
        except Exception:
            pass  # storage failure must not crash runtime
        self._recent.append(record)

    def list_recent(self, limit: int = 100) -> list[dict]:
        items = self._repository.list_recent(limit=limit)
        if items:
            return items
        local_items = list(self._recent)
        local_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return local_items[:limit]

    def get_result(self, scan_id: str) -> dict | None:
        for item in self._recent:
            if item.get("scan_id") == scan_id:
                return item
        return self._repository.get_result(scan_id)

    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict]:
        items = self._repository.list_by_camera(camera_id, limit=limit)
        if items:
            return items
        local_items = [item for item in self._recent if item.get("camera_id") == camera_id]
        local_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return local_items[:limit]

    def list_by_incident(self, incident_id: str, limit: int = 100) -> list[dict]:
        items = self._repository.list_by_incident(incident_id, limit=limit)
        if items:
            return items
        local_items = [item for item in self._recent if item.get("incident_id") == incident_id]
        local_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return local_items[:limit]

    def cleanup(self) -> int:
        cutoff = time.time() - float(self._retention)
        before = len(self._recent)
        fresh = deque(
            (
                item
                for item in self.list_recent(limit=self._max_recent * 2)
                if _created_at_timestamp(item.get("created_at")) > cutoff
            ),
            maxlen=self._max_recent,
        )
        self._recent = fresh
        return max(0, before - len(self._recent))

    def health_check(self) -> dict[str, Any]:
        return self._repository.health_check().to_dict()


def _created_at_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
