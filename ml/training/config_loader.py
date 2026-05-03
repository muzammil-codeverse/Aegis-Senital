"""Load and validate YAML training configs."""
from __future__ import annotations

import yaml
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FIELDS = {
    "dataset_path": str,
    "epochs": int,
    "batch_size": int,
    "img_size": int,
    "model": str,
    "output_path": str,
    "experiment_name": str,
}


@dataclass
class TrainingConfig:
    dataset_path: str
    epochs: int
    batch_size: int
    img_size: int
    model: str
    output_path: str
    experiment_name: str


def load_config(config_path: str) -> TrainingConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if path.suffix not in (".yaml", ".yml"):
        raise ValueError(f"Config must be a YAML file, got: {path.suffix}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Config file is empty or malformed: {config_path}")

    # Validate presence and types
    errors: list[str] = []
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in raw:
            errors.append(f"Missing required field: '{field}'")
            continue
        value = raw[field]
        if value is None or str(value).strip() == "":
            errors.append(f"Field '{field}' must not be empty")
            continue
        try:
            raw[field] = expected_type(value)
        except (ValueError, TypeError):
            errors.append(f"Field '{field}' must be {expected_type.__name__}, got: {value!r}")

    if errors:
        raise ValueError("Config validation failed:\n  " + "\n  ".join(errors))

    # Range checks
    if raw["epochs"] < 1:
        raise ValueError("epochs must be >= 1")
    if raw["batch_size"] < 1:
        raise ValueError("batch_size must be >= 1")
    if raw["img_size"] < 32:
        raise ValueError("img_size must be >= 32")

    return TrainingConfig(**{k: raw[k] for k in REQUIRED_FIELDS})
