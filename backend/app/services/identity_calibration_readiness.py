"""Detect on-disk identity calibration / ReID benchmark artifacts (no fabricated metrics)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def calibration_output_root(config: dict[str, Any] | None) -> Path:
    base = _project_root()
    if config:
        cal = config.get("calibration") or {}
        out = cal.get("output_dir")
        if isinstance(out, str) and out.strip():
            path = Path(out)
            return path if path.is_absolute() else base / path
    return base / "storage" / "identity_calibration"


def snapshot_identity_calibration(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return whether face / ReID calibration artifacts exist under output_dir."""
    root = calibration_output_root(config or {})
    face_calibrated = False
    reid_benchmarked = False
    face_latest: str | None = None
    reid_latest: str | None = None
    try:
        if root.exists():
            face_dirs = sorted(
                (p for p in root.iterdir() if p.is_dir() and p.name.startswith("face_")),
                key=lambda p: p.name,
                reverse=True,
            )
            for child in face_dirs:
                metrics_path = child / "metrics.json"
                if not metrics_path.is_file():
                    continue
                try:
                    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    logger.debug("Skip unreadable metrics %s: %s", metrics_path, exc)
                    continue
                if isinstance(payload, dict):
                    inner = payload.get("metrics")
                    if isinstance(inner, dict) and (inner.get("far") is not None or inner.get("threshold_sweep")):
                        face_calibrated = True
                        face_latest = str(child)
                        break
    except OSError as exc:
        logger.warning("Face calibration scan failed: %s", exc)

    try:
        if root.exists():
            reid_dirs = sorted(
                (p for p in root.iterdir() if p.is_dir() and p.name.startswith("reid_")),
                key=lambda p: p.name,
                reverse=True,
            )
            for child in reid_dirs:
                metrics_path = child / "metrics.json"
                if not metrics_path.is_file():
                    continue
                try:
                    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict) and (payload.get("rank_1") is not None or payload.get("cmc_curve")):
                    reid_benchmarked = True
                    reid_latest = str(child)
                    break
    except OSError as exc:
        logger.warning("ReID benchmark scan failed: %s", exc)

    return {
        "face_calibrated": face_calibrated,
        "reid_benchmarked": reid_benchmarked,
        "output_dir": str(root),
        "face_latest_run": face_latest,
        "reid_latest_run": reid_latest,
    }
