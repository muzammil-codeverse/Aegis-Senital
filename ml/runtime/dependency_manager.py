from __future__ import annotations

import importlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from ml.runtime.model_router import ModelRouter

REQUIRED_DEPENDENCIES = {
    "vector_db": "faiss-cpu OR faiss-gpu",
    "database": "psycopg2 + sqlalchemy + asyncpg",
}
OPTIONAL_DEPENDENCIES = {
    "face_recognition": "insightface",
    "reid_model": "osnet (torchreid)",
}

_BOOT_LOCK = threading.Lock()
_BOOT_VALIDATED = False

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _PROJECT_ROOT / "models" / "registry.json"
_REQUIRED_MODEL_TYPES = ("weapon", "phone")


def _validate_import(module_name: str, label: str, missing: list[str]) -> None:
    try:
        importlib.import_module(module_name)
    except Exception:
        missing.append(label)


def validate_dependencies() -> None:
    missing: list[str] = []
    missing_optional: list[str] = []

    _validate_import("insightface", "insightface", missing_optional)
    _validate_import("torchreid.reid.utils", "osnet (torchreid)", missing_optional)
    _validate_import("faiss", "faiss", missing)
    _validate_import("psycopg2", "postgres drivers", missing)
    _validate_import("sqlalchemy", "sqlalchemy", missing)
    _validate_import("asyncpg", "asyncpg", missing)
    _validate_import("torch", "torch", missing)
    _validate_import("torchvision", "torchvision", missing)
    _validate_import("ultralytics", "ultralytics", missing)
    _validate_import("cv2", "opencv-python", missing)

    if missing_optional:
        logging.getLogger(__name__).warning(
            "Optional dependencies unavailable; related features will run degraded: %s",
            missing_optional,
        )

    if missing:
        raise RuntimeError(
            f"[CRITICAL FAILURE] Missing dependencies: {missing}. "
            "System cannot start in fallback mode."
        )


def validate_cuda_availability() -> None:
    import logging
    from ml.runtime.device_manager import is_cuda_available

    if not is_cuda_available():
        logging.getLogger(__name__).warning(
            "CUDA not available — inference will run on CPU. "
            "Performance will be significantly degraded."
        )


def validate_registry_exists() -> dict:
    if not _REGISTRY_PATH.exists():
        raise RuntimeError(
            f"[CRITICAL FAILURE] Model registry missing: {_REGISTRY_PATH}. "
            "System cannot start without registry.json."
        )
    try:
        registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"[CRITICAL FAILURE] Model registry unreadable: {_REGISTRY_PATH}. "
            f"Error: {exc}"
        ) from exc
    return registry


def validate_model_files_exist(registry: dict) -> None:
    errors: list[str] = []
    for model_type in _REQUIRED_MODEL_TYPES:
        entry = registry.get(model_type)
        if entry is None:
            errors.append(f"Registry missing '{model_type}' entry")
            continue
        model_path = Path(entry.get("path", ""))
        if not model_path.is_absolute():
            model_path = _PROJECT_ROOT / model_path
        if not model_path.exists():
            errors.append(f"Model file missing for '{model_type}': {model_path}")
        metadata_path = Path(entry.get("metadata", ""))
        if not metadata_path.is_absolute():
            metadata_path = _PROJECT_ROOT / metadata_path
        if not metadata_path.exists():
            errors.append(f"Metadata file missing for '{model_type}': {metadata_path}")
    if errors:
        raise RuntimeError(
            f"[CRITICAL FAILURE] Model file validation failed: {errors}. "
            "System cannot start."
        )


def validate_test_inference() -> None:
    import torch
    from ultralytics import YOLO

    device = "cuda" if torch.cuda.is_available() else "cpu"
    registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    for model_type in _REQUIRED_MODEL_TYPES:
        entry = registry.get(model_type)
        if entry is None:
            raise RuntimeError(
                f"[CRITICAL FAILURE] Registry entry for '{model_type}' missing during test inference."
            )
        model_path = Path(entry["path"])
        if not model_path.is_absolute():
            model_path = _PROJECT_ROOT / model_path
        try:
            model = YOLO(str(model_path))
            dummy = torch.zeros((1, 3, 640, 640))
            model(dummy, verbose=False, device=device)
        except Exception as exc:
            raise RuntimeError(
                f"[CRITICAL FAILURE] Test inference failed for '{model_type}' model at {model_path}: {exc}"
            ) from exc


def validate_model_weights_exist() -> dict[str, dict[str, Any]]:
    router = ModelRouter()
    return router.validate_required_models()


def system_boot_check() -> None:
    global _BOOT_VALIDATED
    with _BOOT_LOCK:
        if _BOOT_VALIDATED:
            return
        validate_dependencies()
        try:
            from inference.config_runtime import load_runtime_config
            from ml.runtime.device_manager import require_cuda_if_configured
            require_cuda_if_configured(load_runtime_config("runtime_health"))
        except FileNotFoundError:
            pass
        validate_cuda_availability()
        registry = validate_registry_exists()
        validate_model_files_exist(registry)
        validate_test_inference()
        validate_model_weights_exist()
        _BOOT_VALIDATED = True
