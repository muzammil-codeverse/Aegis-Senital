from __future__ import annotations

import importlib
import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml

from app.repositories.model_registry_repository import get_model_registry_repository
from ml.runtime.model_router import ModelRouter

REQUIRED_DEPENDENCIES = {
    "vector_db": "faiss-cpu OR faiss-gpu",
    "database": "psycopg2 + sqlalchemy + asyncpg",
}
OPTIONAL_DEPENDENCIES = {
    "face_recognition": "insightface + onnxruntime",
    "reid_model": "osnet (torchreid)",
    "segmentation": "SAM2",
}

_BOOT_LOCK = threading.Lock()
_BOOT_VALIDATED = False

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_MODEL_TYPES = ("weapon", "phone")


def _profile(profile: str | None = None) -> str:
    return (profile or os.environ.get("APP_ENV") or "development").lower()


def _validate_import(module_name: str, label: str, missing: list[str]) -> None:
    try:
        importlib.import_module(module_name)
    except Exception:
        missing.append(label)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_identity_cfg() -> dict[str, Any]:
    payload = _load_yaml(_PROJECT_ROOT / "configs" / "runtime" / "identity.yaml")
    root = payload.get("identity", payload)
    return root if isinstance(root, dict) else {}


def get_identity_dependency_status(
    profile: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_profile = _profile(profile)
    identity_cfg = (config or _load_identity_cfg()) or {}
    fail_open = bool(identity_cfg.get("fail_open", True))

    def _module_status(enabled: bool, modules: list[str], label: str) -> dict[str, Any]:
        errors = []
        available = True
        for module in modules:
            try:
                importlib.import_module(module)
            except Exception as exc:
                available = False
                errors.append(f"{module}: {exc}")
        return {
            "enabled": enabled,
            "available": available if enabled else True,
            "required": enabled and (resolved_profile == "production" or not fail_open),
            "label": label,
            "errors": errors,
        }

    face_enabled = bool(identity_cfg.get("face", {}).get("enabled", False))
    reid_enabled = bool(identity_cfg.get("reid", {}).get("enabled", False))
    liveness_enabled = bool(identity_cfg.get("liveness", {}).get("enabled", False))
    liveness_provider = str(identity_cfg.get("liveness", {}).get("provider", "pending"))

    face = _module_status(face_enabled, ["insightface", "onnxruntime"], "identity.face")
    if face_enabled and face["available"]:
        try:
            face_model = ModelRouter().get_model("face")
            face["model_path"] = face_model.get("resolved_path")
        except Exception as exc:
            face["available"] = False
            face["errors"].append(f"face model bundle: {exc}")
    reid = _module_status(reid_enabled, ["torch", "torchreid.reid.utils"], "identity.reid")
    liveness = {
        "enabled": liveness_enabled,
        "available": not liveness_enabled,
        "required": liveness_enabled and resolved_profile == "production",
        "label": "identity.liveness",
        "errors": [] if not liveness_enabled else [f"provider '{liveness_provider}' not integrated"],
        "provider": liveness_provider,
    }

    failures = []
    warnings = []
    for item in (face, reid, liveness):
        if not item["enabled"]:
            continue
        if item["available"]:
            continue
        if item["required"]:
            failures.append(f"{item['label']}: {', '.join(item['errors'])}")
        else:
            warnings.append(f"{item['label']}: {', '.join(item['errors'])}")

    if failures:
        overall = "failed"
    elif warnings:
        overall = "degraded"
    elif not any((face_enabled, reid_enabled, liveness_enabled)):
        overall = "disabled"
    else:
        overall = "healthy"

    return {
        "profile": resolved_profile,
        "fail_open": fail_open,
        "face": face,
        "reid": reid,
        "liveness": liveness,
        "status": overall,
        "failures": failures,
        "warnings": warnings,
    }


def validate_identity_dependencies(profile: str | None = None) -> dict[str, Any]:
    status = get_identity_dependency_status(profile=profile)
    logger = logging.getLogger(__name__)
    for warning in status["warnings"]:
        logger.warning("Identity runtime degraded: %s", warning)
    if status["failures"]:
        raise RuntimeError(
            "[CRITICAL FAILURE] Identity dependencies unavailable: "
            + "; ".join(status["failures"])
        )
    return status


def validate_dependencies(profile: str | None = None) -> None:
    missing: list[str] = []
    missing_optional: list[str] = []

    _validate_import("faiss", "faiss", missing)
    _validate_import("psycopg2", "postgres drivers", missing)
    _validate_import("sqlalchemy", "sqlalchemy", missing)
    _validate_import("asyncpg", "asyncpg", missing)
    _validate_import("torch", "torch", missing)
    _validate_import("torchvision", "torchvision", missing)
    _validate_import("ultralytics", "ultralytics", missing)
    _validate_import("cv2", "opencv-python", missing)

    _validate_import("insightface", "insightface", missing_optional)
    _validate_import("onnxruntime", "onnxruntime", missing_optional)
    _validate_import("torchreid.reid.utils", "osnet (torchreid)", missing_optional)
    validate_segmentation_dependencies(profile=profile)
    validate_identity_dependencies(profile=profile)

    if missing_optional:
        logging.getLogger(__name__).warning(
            "Optional dependencies unavailable; related features may run degraded: %s",
            missing_optional,
        )
    if missing:
        raise RuntimeError(
            f"[CRITICAL FAILURE] Missing dependencies: {missing}. System cannot start."
        )


def validate_segmentation_dependencies(profile: str | None = None) -> None:
    resolved_profile = _profile(profile)
    config_path = _PROJECT_ROOT / "configs" / "runtime" / "segmentation.yaml"
    if not config_path.exists():
        if resolved_profile == "production":
            raise RuntimeError(
                f"[CRITICAL FAILURE] Segmentation config missing in production: {config_path}"
            )
        logging.getLogger(__name__).warning(
            "Segmentation config missing; segmentation disabled/degraded: %s",
            config_path,
        )
        return

    cfg = _load_yaml(config_path)
    seg = cfg.get("segmentation", cfg)
    if not isinstance(seg, dict) or not bool(seg.get("enabled", False)):
        return
    if str(seg.get("provider", "sam2")).lower() != "sam2":
        message = f"Unsupported segmentation provider: {seg.get('provider')}"
        if resolved_profile == "production":
            raise RuntimeError(f"[CRITICAL FAILURE] {message}")
        logging.getLogger(__name__).warning(message)
        return

    missing: list[str] = []
    try:
        importlib.import_module("sam2")
    except Exception:
        missing.append("sam2 package")

    sam2_cfg = seg.get("sam2", {}) if isinstance(seg.get("sam2"), dict) else {}
    checkpoint = _PROJECT_ROOT / sam2_cfg.get("checkpoint_path", "models/segmentation/sam2/checkpoint.pt")
    model_config = _PROJECT_ROOT / sam2_cfg.get("model_config", "configs/segmentation/sam2.yaml")
    if not checkpoint.exists():
        missing.append(f"SAM2 checkpoint: {checkpoint}")
    if not model_config.exists():
        missing.append(f"SAM2 model config: {model_config}")
    if not missing:
        return

    message = (
        "Segmentation is enabled but SAM2 dependencies/assets are unavailable: "
        f"{missing}"
    )
    if resolved_profile == "production":
        raise RuntimeError(
            f"[CRITICAL FAILURE] {message}. Install SAM2/checkpoint/config or disable segmentation."
        )
    logging.getLogger(__name__).warning("%s Runtime will degrade loudly.", message)


def validate_cuda_availability() -> None:
    from ml.runtime.device_manager import is_cuda_available

    if not is_cuda_available():
        logging.getLogger(__name__).warning(
            "CUDA not available - inference will run on CPU. Performance will be degraded."
        )


def validate_registry_exists() -> list[dict[str, Any]]:
    repository = get_model_registry_repository()
    if not repository.is_available():
        raise RuntimeError(
            "[CRITICAL FAILURE] Model registry repository is unavailable. "
            f"Backend={repository.storage_backend}."
        )
    try:
        entries = [entry.to_dict() for entry in repository.list_entries()]
    except Exception as exc:
        raise RuntimeError(
            "[CRITICAL FAILURE] Model registry repository is unreadable. "
            f"Error: {exc}"
        ) from exc
    if not entries:
        raise RuntimeError("[CRITICAL FAILURE] Model registry is empty.")
    return entries


def validate_model_files_exist(registry: list[dict[str, Any]]) -> None:
    del registry
    errors: list[str] = []
    router = ModelRouter()
    for model_type in _REQUIRED_MODEL_TYPES:
        try:
            entry = router.get_model(model_type)
        except Exception as exc:
            errors.append(f"Registry missing '{model_type}' model: {exc}")
            continue
        model_path = Path(entry.get("resolved_path") or entry.get("path") or "")
        if not model_path.is_absolute():
            model_path = _PROJECT_ROOT / model_path
        if not model_path.exists():
            errors.append(f"Model file missing for '{model_type}': {model_path}")
        metadata_ref = entry.get("metadata")
        if isinstance(metadata_ref, str) and metadata_ref:
            metadata_path = Path(metadata_ref)
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
    router = ModelRouter()
    for model_type in _REQUIRED_MODEL_TYPES:
        entry = router.get_model(model_type)
        model_path = Path(entry.get("resolved_path") or entry.get("path") or "")
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
