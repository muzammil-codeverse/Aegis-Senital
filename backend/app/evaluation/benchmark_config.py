"""Phase 25/26B — Benchmark configuration loader."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: Any, override: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_evaluation_config(config_path: str | Path) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Evaluation config not found: {path}")
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    local_override_path = path.with_name("evaluation.local.yaml")
    if path.name == "evaluation.yaml" and local_override_path.exists():
        with open(local_override_path, encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        config = _deep_merge(config, override)
    return config


def load_regression_policy(config: dict) -> dict:
    return config.get("regression_policy", {
        "detection_map_drop_warn": 0.02,
        "detection_map_drop_fail": 0.05,
        "latency_p95_increase_warn_percent": 15,
        "latency_p95_increase_fail_percent": 30,
        "false_positive_increase_warn_percent": 20,
    })


def resolve_device(config: dict, override: str | None = None) -> str:
    if override:
        return override
    device = config.get("evaluation", {}).get("device", "cuda")
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                if config.get("evaluation", {}).get("allow_cpu_fallback", True):
                    return "cpu"
                raise RuntimeError("CUDA not available and allow_cpu_fallback=false")
        except ImportError:
            return "cpu"
    return device


def get_git_commit() -> str | None:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except Exception:
        pass
    return None


def config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def make_run_dir(config: dict, run_id: str) -> Path:
    output_dir = config.get("evaluation", {}).get("output_dir", "storage/evaluation_runs")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_config_snapshot(run_dir: Path, config: dict) -> None:
    if not config:
        return
    out = run_dir / "config_snapshot.yaml"
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)
