"""
ModelRegistry — runtime model lifecycle manager backed by models/registry.json.

Responsibilities:
- Load and validate the static registry on startup.
- Provide list / get / patch operations on model records.
- Track per-model health status (set externally by loader threads).
- Accumulate per-model inference statistics (latency, call count).
- Support atomic reload from disk without downtime.

Thread safety: all mutable state is guarded by a reentrant lock so that
API routes and background inference threads can read concurrently.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Runtime model lifecycle manager backed by models/registry.json."""

    def __init__(self, registry_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        if registry_path is None:
            base = Path(__file__).resolve().parent.parent.parent
            registry_path = str(base / "models" / "registry.json")
        self._registry_path = registry_path
        self._models: Dict[str, Dict] = {}       # model_id -> flattened model record
        self._health: Dict[str, Dict] = {}       # model_id -> health info
        self._inference_stats: Dict[str, Dict] = {}  # model_id -> inference stats
        self._loaded = False

    # ------------------------------------------------------------------
    # Load / reload
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load and validate registry from disk."""
        with self._lock:
            try:
                with open(self._registry_path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._models = {}
                for task_name, versions in raw.items():
                    if isinstance(versions, dict):
                        first_val = next(iter(versions.values()), {})
                        if isinstance(first_val, dict) and "path" in first_val:
                            # Versioned: {task: {v1: {...}, v2: {...}}}
                            for version, meta in versions.items():
                                model_id = f"{task_name}/{version}"
                                record = self._build_record(model_id, task_name, version, meta)
                                self._models[model_id] = record
                        else:
                            # Direct model at task level
                            model_id = task_name
                            record = self._build_record(model_id, task_name, "v1", versions)
                            self._models[model_id] = record
                self._loaded = True
                logger.info(
                    "ModelRegistry loaded %d models from %s",
                    len(self._models),
                    self._registry_path,
                )
            except FileNotFoundError:
                logger.warning(
                    "Registry file not found: %s. Starting empty.", self._registry_path
                )
                self._models = {}
                self._loaded = True
            except Exception as exc:
                logger.error("Failed to load model registry: %s", exc)
                self._loaded = False

    def reload(self) -> None:
        """Reload from disk; preserves existing health and inference stats."""
        with self._lock:
            self._loaded = False
        self.load()

    # ------------------------------------------------------------------
    # Record construction helpers
    # ------------------------------------------------------------------

    def _build_record(
        self, model_id: str, task: str, version: str, meta: dict
    ) -> dict:
        task_map = {
            "weapon_detector": "weapon_detection",
            "phone_detector": "phone_detection",
            "face_recognition": "face_embedding",
        }
        inferred_task = task_map.get(task, task)
        now = time.time()
        record = {
            "model_id": model_id,
            "task": meta.get("task", inferred_task),
            "name": meta.get("model_name", task),
            "version": meta.get("version", version),
            "path": meta.get("path", ""),
            "format": self._infer_format(meta.get("path", "")),
            "enabled": meta.get("enabled", True),
            "device_preference": meta.get("device_preference", "auto"),
            "classes": meta.get("classes", []),
            "input_size": meta.get("input_size", None),
            "confidence_threshold": meta.get("confidence_threshold", 0.30),
            "required": meta.get("required", False),
            "metadata": {
                k: v
                for k, v in meta.items()
                if k not in {
                    "model_id", "task", "name", "version", "path", "format",
                    "enabled", "device_preference", "classes", "input_size",
                    "confidence_threshold", "required",
                }
            },
            "registered_at": now,
        }
        # Initialise health slot if first time seeing this model_id
        if model_id not in self._health:
            self._health[model_id] = {
                "status": "unknown",
                "detail": None,
                "last_checked": None,
                "load_error": None,
                "device": None,
            }
        # Initialise inference stats if first time seeing this model_id
        if model_id not in self._inference_stats:
            self._inference_stats[model_id] = {
                "last_inference_at": None,
                "total_inferences": 0,
                "avg_latency_ms": None,
                "_latency_sum": 0.0,
                "_latency_count": 0,
            }
        return record

    @staticmethod
    def _infer_format(path: str) -> str:
        if not path:
            return "unknown"
        if path.endswith(".pt") or path.endswith(".pth"):
            return "pt"
        if path.endswith(".onnx"):
            return "onnx"
        if path.endswith(".engine"):
            return "engine"
        return "directory"

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def list_models(
        self, task: Optional[str] = None, enabled_only: bool = False
    ) -> List[dict]:
        with self._lock:
            results = []
            for model_id, record in self._models.items():
                if task and record.get("task") != task:
                    continue
                if enabled_only and not record.get("enabled", True):
                    continue
                results.append(self._enrich(model_id, record))
            return results

    def get_model(self, model_id: str) -> Optional[dict]:
        with self._lock:
            if model_id not in self._models:
                return None
            return self._enrich(model_id, self._models[model_id])

    def get_active_models(self, task: Optional[str] = None) -> List[dict]:
        """Return all enabled models, optionally filtered by task."""
        return self.list_models(task=task, enabled_only=True)

    def validate_model_files(self) -> Dict[str, bool]:
        """Check whether model files exist on disk. Returns {model_id: bool}."""
        results: Dict[str, bool] = {}
        with self._lock:
            base = Path(__file__).resolve().parent.parent.parent
            for model_id, record in self._models.items():
                path = record.get("path", "")
                if not path:
                    results[model_id] = False
                    continue
                full = base / path
                results[model_id] = full.exists()
        return results

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def update_model_health(
        self,
        model_id: str,
        status: str,
        detail: Optional[str] = None,
        device: Optional[str] = None,
        load_error: Optional[str] = None,
    ) -> None:
        """Update health status for a model (called by loader threads)."""
        with self._lock:
            if model_id not in self._health:
                self._health[model_id] = {}
            self._health[model_id].update(
                {
                    "status": status,
                    "detail": detail,
                    "last_checked": time.time(),
                    "device": device,
                    "load_error": load_error,
                }
            )

    def record_inference(self, model_id: str, latency_ms: Optional[float] = None) -> None:
        """Accumulate inference call and optional latency sample."""
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
                stats["avg_latency_ms"] = (
                    stats["_latency_sum"] / stats["_latency_count"]
                )

    def patch_model(self, model_id: str, updates: dict) -> bool:
        """
        Patch allowed runtime fields on a model record.

        Allowed keys: enabled, confidence_threshold, device_preference.
        Returns True on success, False if model not found.
        """
        allowed = {"enabled", "confidence_threshold", "device_preference"}
        with self._lock:
            if model_id not in self._models:
                return False
            for k, v in updates.items():
                if k in allowed:
                    self._models[model_id][k] = v
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enrich(self, model_id: str, record: dict) -> dict:
        """Return a copy of record augmented with health and inference data."""
        h = self._health.get(model_id, {})
        s = self._inference_stats.get(model_id, {})
        return {
            **record,
            "health": {
                "status": h.get("status", "unknown"),
                "detail": h.get("detail"),
                "last_checked": h.get("last_checked"),
                "device": h.get("device"),
                "load_error": h.get("load_error"),
            },
            "inference": {
                "last_inference_at": s.get("last_inference_at"),
                "total_inferences": s.get("total_inferences", 0),
                "avg_latency_ms": s.get("avg_latency_ms"),
            },
        }

    def to_dict(self) -> dict:
        """Full registry snapshot for diagnostics."""
        with self._lock:
            return {
                "loaded": self._loaded,
                "model_count": len(self._models),
                "models": [
                    self._enrich(mid, rec) for mid, rec in self._models.items()
                ],
            }


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_registry_instance: Optional[ModelRegistry] = None
_registry_lock = threading.Lock()


def get_model_registry() -> ModelRegistry:
    """Return (or lazily create) the process-wide ModelRegistry singleton."""
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = ModelRegistry()
            _registry_instance.load()
        return _registry_instance
