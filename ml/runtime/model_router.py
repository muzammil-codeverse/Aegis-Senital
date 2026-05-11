from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from app.repositories.model_registry_repository import get_model_registry_repository

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FACE_MODEL_PATH = "models/buffalo_l"


class ModelRouter:
    """
    Registry-backed model selector with hot reload and simple A/B routing.
    """

    _ALIASES = {
        "weapon": "weapon_detector",
        "weapons": "weapon_detector",
        "phone": "phone_detector",
        "device": "phone_detector",
        "face": "face_recognition",
        "identity": "face_recognition",
        "face_recognition": "face_recognition",
    }
    _REQUIRED_TASKS = ("weapon", "phone")

    def __init__(self, registry_path: str | Path = "models/registry.json") -> None:
        del registry_path
        self._repository = get_model_registry_repository()

    def get_model(self, task: str = "weapon", version: str = "latest", route_key: str | None = None) -> dict[str, Any]:
        model_key = self._ALIASES.get(task, task)
        versions = self._repository.grouped_entries().get(model_key) or {}
        if not versions and model_key == "face_recognition":
            payload = self._face_model_payload()
            resolved_path = self.load_model_or_crash(payload["path"])
            return {
                "task": task,
                "model_key": model_key,
                "selected_version": payload["version"],
                "resolved_path": str(resolved_path),
                **payload,
            }
        if not versions:
            raise KeyError(f"No model registered for task '{task}'.")

        if version == "latest":
            selected_version = self._latest_version(versions)
        elif version == "ab":
            selected_version = self._ab_version(versions, route_key=route_key)
        else:
            selected_version = version

        payload = versions.get(selected_version)
        if payload is None:
            raise KeyError(f"Version '{selected_version}' is not registered for task '{task}'.")
        resolved_path = self.load_model_or_crash(payload["path"])
        return {
            "task": task,
            "model_key": model_key,
            "selected_version": selected_version,
            "resolved_path": str(resolved_path),
            **payload,
        }

    def validate_required_models(self) -> dict[str, dict[str, Any]]:
        return {task: self.get_model(task) for task in self._REQUIRED_TASKS}

    @staticmethod
    def _latest_version(versions: dict[str, Any]) -> str:
        def _sort_key(item: tuple[str, Any]) -> tuple[str, str]:
            name, payload = item
            created_at = payload.get("created_at", "")
            return created_at, name

        return sorted(versions.items(), key=_sort_key)[-1][0]

    @staticmethod
    def _ab_version(versions: dict[str, Any], route_key: str | None = None) -> str:
        ordered = sorted(versions)
        if len(ordered) == 1:
            return ordered[0]
        seed = route_key or "default"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        index = int(digest, 16) % len(ordered)
        return ordered[index]

    @staticmethod
    def load_model_or_crash(model_path: str | Path) -> Path:
        path = Path(model_path)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        path = path.resolve()
        if not path.exists():
            raise RuntimeError(f"Model missing: {path}")
        if path.is_dir():
            contains_weights = any(path.rglob("*.onnx")) or any(path.rglob("*.pt"))
            if not contains_weights:
                raise RuntimeError(f"Model bundle missing weights: {path}")
            return path
        if path.suffix.lower() not in {".pt", ".onnx"}:
            raise RuntimeError(f"Unsupported model format: {path}")
        return path

    @staticmethod
    def _face_model_payload() -> dict[str, Any]:
        path = os.getenv("AEGIS_FACE_MODEL_PATH") or os.getenv("FACE_MODEL_PATH") or _DEFAULT_FACE_MODEL_PATH
        return {
            "model_name": "face_recognition",
            "version": "required",
            "path": path,
            "framework": "InsightFace",
            "notes": "Required face-recognition model bundle for identity fusion.",
        }
