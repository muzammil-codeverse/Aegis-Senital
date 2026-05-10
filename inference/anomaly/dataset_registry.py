from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_KAGGLE_CONFIG_PATH = "configs/evaluation/kaggle_anomaly_sources.yaml"
_ROBOFLOW_CONFIG_PATH = "configs/evaluation/roboflow_anomaly_sources.yaml"


def load_kaggle_sources() -> dict:
    return _load_yaml(_KAGGLE_CONFIG_PATH)


def load_roboflow_sources() -> dict:
    return _load_yaml(_ROBOFLOW_CONFIG_PATH)


def list_available_datasets(base_dir: str = "datasets/raw/anomaly") -> dict[str, dict]:
    """Return which configured datasets are present on disk."""
    sources = load_kaggle_sources()
    result: dict[str, dict] = {}
    for name, cfg in sources.items():
        raw_dir = cfg.get("raw_dir", "")
        present = os.path.isdir(raw_dir) and bool(list(Path(raw_dir).iterdir()) if Path(raw_dir).exists() else [])
        result[name] = {
            "name": name,
            "role": cfg.get("role", ""),
            "required": cfg.get("required", False),
            "present": present,
            "raw_dir": raw_dir,
        }
    return result


def validate_required_datasets() -> list[str]:
    """Return list of missing required dataset names."""
    missing = []
    for name, info in list_available_datasets().items():
        if info["required"] and not info["present"]:
            missing.append(name)
    return missing


def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        logger.warning("[DatasetRegistry] Config not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("[DatasetRegistry] Failed to parse %s: %s", path, exc)
        return {}
