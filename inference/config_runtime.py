from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


RUNTIME_CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs" / "runtime"


def load_runtime_config(name: str) -> dict[str, Any]:
    path = RUNTIME_CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Runtime config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid runtime config format: {path}")
    return data
