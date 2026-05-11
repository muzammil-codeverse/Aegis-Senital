from __future__ import annotations

import threading
from typing import Any

from app.models.uploaded_video_models import UploadedVideoProcessingStatus


class UploadedVideoProgressService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._statuses: dict[str, UploadedVideoProcessingStatus] = {}

    def update(self, status: UploadedVideoProcessingStatus | dict[str, Any]) -> UploadedVideoProcessingStatus:
        payload = status if isinstance(status, UploadedVideoProcessingStatus) else UploadedVideoProcessingStatus.model_validate(status)
        with self._lock:
            self._statuses[payload.session_id] = payload
        return payload

    def get(self, session_id: str) -> UploadedVideoProcessingStatus | None:
        with self._lock:
            return self._statuses.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._statuses.pop(session_id, None)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            items = list(self._statuses.values())
        return {
            "active_sessions": sum(1 for item in items if item.active),
            "completed_sessions": sum(1 for item in items if item.status == "completed"),
            "failed_sessions": sum(1 for item in items if item.status == "failed"),
        }


_PROGRESS_SERVICE: UploadedVideoProgressService | None = None
_PROGRESS_LOCK = threading.Lock()


def get_uploaded_video_progress_service() -> UploadedVideoProgressService:
    global _PROGRESS_SERVICE
    with _PROGRESS_LOCK:
        if _PROGRESS_SERVICE is None:
            _PROGRESS_SERVICE = UploadedVideoProgressService()
        return _PROGRESS_SERVICE
