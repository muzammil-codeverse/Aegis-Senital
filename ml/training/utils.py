"""Logging helpers, path utilities, and dataset validation."""
from __future__ import annotations

import logging
import yaml
from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str, log_dir: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(Path(log_dir) / f"{name}.log")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def validate_path(path: str, must_be_file: bool = False, label: str = "path") -> Path:
    p = Path(path)
    if must_be_file:
        if not p.is_file():
            raise FileNotFoundError(f"{label} does not exist or is not a file: {p}")
    else:
        if not p.exists():
            raise FileNotFoundError(f"{label} does not exist: {p}")
    return p


# ---------------------------------------------------------------------------
# Dataset validation
# ---------------------------------------------------------------------------

def validate_dataset(data_yaml_path: str) -> None:
    """
    Validate a YOLO dataset described by a data.yaml file.

    Checks:
    - Required keys present (train, val, nc, names)
    - Image directories exist and contain images
    - Every image has a corresponding label file
    - Each label line has exactly 5 values
    - class_id < nc
    - Bounding-box coordinates are in [0, 1]
    """
    data_path = validate_path(data_yaml_path, must_be_file=True, label="dataset_path")

    with open(data_path) as f:
        data = yaml.safe_load(f)

    for key in ("train", "val", "nc", "names"):
        if key not in data:
            raise ValueError(f"data.yaml missing required key: '{key}'")

    nc: int = int(data["nc"])
    base_dir = data_path.parent

    for split in ("train", "val"):
        img_dir = Path(data[split])
        if not img_dir.is_absolute():
            img_dir = base_dir / img_dir

        if not img_dir.exists():
            raise FileNotFoundError(f"[{split}] Image directory not found: {img_dir}")

        images = [p for p in img_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS]
        if not images:
            raise ValueError(f"[{split}] No images found in {img_dir}")

        # Derive label directory (standard YOLO: .../images/... → .../labels/...)
        label_dir = Path(str(img_dir).replace("images", "labels", 1))

        missing: list[str] = []
        invalid: list[str] = []

        for img in images:
            lbl = label_dir / (img.stem + ".txt")
            if not lbl.exists():
                missing.append(img.name)
                continue

            with open(lbl) as f:
                for line_no, raw in enumerate(f, 1):
                    line = raw.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) != 5:
                        invalid.append(f"{lbl.name}:{line_no} — expected 5 values, got {len(parts)}")
                        continue
                    try:
                        cls = int(parts[0])
                        coords = [float(v) for v in parts[1:]]
                    except ValueError:
                        invalid.append(f"{lbl.name}:{line_no} — non-numeric values")
                        continue
                    if cls >= nc:
                        invalid.append(f"{lbl.name}:{line_no} — class_id {cls} >= nc {nc}")
                    if not all(0.0 <= c <= 1.0 for c in coords):
                        invalid.append(f"{lbl.name}:{line_no} — coordinates outside [0,1]")

        if missing:
            sample = missing[:5]
            raise ValueError(
                f"[{split}] {len(missing)} images missing label files. "
                f"First {len(sample)}: {sample}"
            )
        if invalid:
            sample = invalid[:5]
            raise ValueError(
                f"[{split}] {len(invalid)} invalid label lines. "
                f"First {len(sample)}: {sample}"
            )
