"""
Runtime model lifecycle manager backed by the model-registry repository.

Reads flow through `backend.app.repositories.model_registry_repository`
so file and PostgreSQL backends share one authoritative abstraction.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.repositories.model_registry_repository import (
    FileModelRegistryRepository,
    ModelRegistryEntry,
    ModelRegistryRepository,
    get_model_registry_repository,
)

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(
        self,
        registry_path: str | None = None,
        *,
        repository: ModelRegistryRepository | None = None,
    ) -> None:
        self._lock = threading.RLock()
        if repository is not None:
            self._repository = repository
        elif registry_path is not None:
            self._repository = FileModelRegistryRepository(registry_path)
        else:
            self._repository = get_model_registry_repository()
        self._models: dict[str, dict[str, Any]] = {}
        self._health: dict[str, dict[str, Any]] = {}
        self._inference_stats: dict[str, dict[str, Any]] = {}
        self._loaded = False

    @property
    def storage_backend(self) -> str:
        return self._repository.storage_backend

    def load(self) -> None:
        with self._lock:
            try:
                entries = self._repository.list_entries()
                self._models = {}
                for entry in entries:
                    record = self._build_record(entry)
                    self._models[record["model_id"]] = record
                self._loaded = True
                logger.info(
                    "ModelRegistry loaded %d models from %s backend",
                    len(self._models),
                    self._repository.storage_backend,
                )
            except Exception as exc:
                logger.error("Failed to load model registry: %s", exc)
                self._loaded = False

    def reload(self) -> None:
        with self._lock:
            self._loaded = False
        self.load()

    def _build_record(self, entry: ModelRegistryEntry) -> dict[str, Any]:
        task_map = {
            "weapon_detector": "weapon_detection",
            "phone_detector": "phone_detection",
            "face_recognition": "face_embedding",
        }
        inferred_task = task_map.get(entry.model_key, entry.model_key)
        metadata = dict(entry.metadata or {})
        now = time.time()
        model_id = entry.model_id
        if model_id not in self._health:
            self._health[model_id] = {
                "status": "unknown",
                "detail": None,
                "last_checked": None,
                "load_error": None,
                "device": None,
            }
        if model_id not in self._inference_stats:
            self._inference_stats[model_id] = {
                "last_inference_at": None,
                "total_inferences": 0,
                "avg_latency_ms": None,
                "_latency_sum": 0.0,
                "_latency_count": 0,
            }
        return {
            "model_id": model_id,
            "task": metadata.get("task", inferred_task),
            "name": entry.model_name,
            "version": entry.version,
            "path": entry.path,
            "format": self._infer_format(entry.path),
            "enabled": metadata.get("enabled", True),
            "device_preference": metadata.get("device_preference", "auto"),
            "classes": metadata.get("classes", []),
            "input_size": metadata.get("input_size"),
            "confidence_threshold": metadata.get("confidence_threshold", 0.30),
            "required": metadata.get("required", False),
            "metadata": metadata,
            "registered_at": metadata.get("created_at", entry.created_at or now),
            "backend": self._repository.storage_backend,
        }

    @staticmethod
    def _infer_format(path: str) -> str:
        if not path:
            return "unknown"
        if path.endswith((".pt", ".pth")):
            return "pt"
        if path.endswith(".onnx"):
            return "onnx"
        if path.endswith(".engine"):
            return "engine"
        return "directory"

    def list_models(self, task: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            results: list[dict[str, Any]] = []
            for model_id, record in self._models.items():
                if task and record.get("task") != task:
                    continue
                if enabled_only and not record.get("enabled", True):
                    continue
                results.append(self._enrich(model_id, record))
            return results

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._models.get(model_id)
            if record is None:
                return None
            return self._enrich(model_id, record)

    def get_active_models(self, task: str | None = None) -> list[dict[str, Any]]:
        return self.list_models(task=task, enabled_only=True)

    def validate_model_files(self) -> dict[str, bool]:
        from pathlib import Path

        results: dict[str, bool] = {}
        with self._lock:
            base = Path(__file__).resolve().parent.parent.parent
            for model_id, record in self._models.items():
                path = record.get("path", "")
                if not path:
                    results[model_id] = False
                    continue
                full = base / path if not Path(path).is_absolute() else Path(path)
                results[model_id] = full.exists()
        return results

    def update_model_health(
        self,
        model_id: str,
        status: str,
        detail: str | None = None,
        device: str | None = None,
        load_error: str | None = None,
    ) -> None:
        with self._lock:
            self._health.setdefault(model_id, {})
            self._health[model_id].update(
                {
                    "status": status,
                    "detail": detail,
                    "last_checked": time.time(),
                    "device": device,
                    "load_error": load_error,
                }
            )

    def record_inference(self, model_id: str, latency_ms: float | None = None) -> None:
        with self._lock:
            stats = self._inference_stats.setdefault(
                model_id,
                {
                    "last_inference_at": None,
                    "total_inferences": 0,
                    "avg_latency_ms": None,
                    "_latency_sum": 0.0,
                    "_latency_count": 0,
                },
            )
            stats["last_inference_at"] = time.time()
            stats["total_inferences"] += 1
            if latency_ms is not None:
                stats["_latency_sum"] += latency_ms
                stats["_latency_count"] += 1
                stats["avg_latency_ms"] = stats["_latency_sum"] / stats["_latency_count"]

    def patch_model(self, model_id: str, updates: dict[str, Any]) -> bool:
        allowed = {"enabled", "confidence_threshold", "device_preference"}
        with self._lock:
            if model_id not in self._models:
                return False
            for key, value in updates.items():
                if key in allowed:
                    self._models[model_id][key] = value
            return True

    def _enrich(self, model_id: str, record: dict[str, Any]) -> dict[str, Any]:
        health = self._health.get(model_id, {})
        stats = self._inference_stats.get(model_id, {})
        return {
            **record,
            "health": {
                "status": health.get("status", "unknown"),
                "detail": health.get("detail"),
                "last_checked": health.get("last_checked"),
                "device": health.get("device"),
                "load_error": health.get("load_error"),
            },
            "inference": {
                "last_inference_at": stats.get("last_inference_at"),
                "total_inferences": stats.get("total_inferences", 0),
                "avg_latency_ms": stats.get("avg_latency_ms"),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "loaded": self._loaded,
                "backend": self._repository.storage_backend,
                "model_count": len(self._models),
                "models": [self._enrich(model_id, record) for model_id, record in self._models.items()],
            }


_registry_instance: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_model_registry() -> ModelRegistry:
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = ModelRegistry()
            _registry_instance.load()
        return _registry_instance
