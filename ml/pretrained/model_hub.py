from __future__ import annotations
import hashlib
import json
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PRETRAINED_DIR = _PROJECT_ROOT / "models" / "pretrained"

# Catalogue of known external model sources with version-locked URLs.
# Add entries here when new pretrained weights are needed.
_KNOWN_MODELS: dict[str, dict] = {
    "yolov8n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
        "filename": "yolov8n.pt",
        "classes": ["coco-80"],
        "framework": "YOLOv8",
        "description": "YOLOv8 nano — COCO general-purpose baseline",
    },
    "yolov8s": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt",
        "filename": "yolov8s.pt",
        "classes": ["coco-80"],
        "framework": "YOLOv8",
        "description": "YOLOv8 small — COCO general-purpose baseline",
    },
    "yolov8m": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt",
        "filename": "yolov8m.pt",
        "classes": ["coco-80"],
        "framework": "YOLOv8",
        "description": "YOLOv8 medium — COCO general-purpose baseline",
    },
}


def download_model(
    name: str,
    dest_dir: Path | str | None = None,
    expected_md5: str | None = None,
) -> Path:
    """
    Download a known pretrained model by catalogue *name*.

    The downloaded file is placed in *dest_dir* (default: models/pretrained/<name>/)
    and auto-registered in the model registry so it appears alongside trained models.

    Parameters
    ----------
    name            Key in _KNOWN_MODELS catalogue.
    dest_dir        Override download destination directory.
    expected_md5    If supplied, the download is validated before returning;
                    the corrupted file is deleted on mismatch.

    Returns
    -------
    Absolute Path to the downloaded file.

    Raises
    ------
    KeyError            Unknown model name.
    ValueError          MD5 mismatch (file removed automatically).
    urllib.error.URLError  Network failure.
    """
    if name not in _KNOWN_MODELS:
        raise KeyError(f"Unknown pretrained model '{name}'. Known: {sorted(_KNOWN_MODELS)}")

    info = _KNOWN_MODELS[name]
    target_dir = Path(dest_dir) if dest_dir else (_PRETRAINED_DIR / name)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / info["filename"]

    if dest_path.exists():
        logger.info(f"model_hub: '{name}' already present at {dest_path}, skipping download")
    else:
        logger.info(json.dumps({
            "event": "model_download_start",
            "name": name,
            "url": info["url"],
            "dest": str(dest_path),
        }))
        urllib.request.urlretrieve(info["url"], dest_path)
        logger.info(json.dumps({
            "event": "model_download_complete",
            "name": name,
            "path": str(dest_path),
            "size_bytes": dest_path.stat().st_size,
        }))

    if expected_md5 and not validate_checksum(dest_path, expected_md5):
        dest_path.unlink(missing_ok=True)
        raise ValueError(
            f"MD5 mismatch for '{name}'. Corrupted file removed. Please re-download."
        )

    register_external_model(
        name=name,
        path=dest_path,
        classes=info.get("classes", []),
        framework=info.get("framework", "YOLOv8"),
        description=info.get("description", ""),
    )
    return dest_path


def validate_checksum(path: Path | str, expected_md5: str) -> bool:
    """
    Return True if the file at *path* matches the expected MD5 hex digest.

    Reads in 8 KB chunks to avoid loading large model files into memory.
    """
    p = Path(path)
    if not p.exists():
        logger.warning(f"validate_checksum: file not found: {path}")
        return False
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected_md5:
        logger.warning(json.dumps({
            "event": "checksum_mismatch",
            "path": str(path),
            "expected": expected_md5,
            "actual": actual,
        }))
        return False
    return True


def register_external_model(
    name: str,
    path: Path | str,
    version: str = "external",
    classes: list[str] | None = None,
    framework: str = "YOLOv8",
    **extra: object,
) -> dict:
    """
    Register an externally sourced model artifact in the unified model registry.

    This makes pretrained weights visible alongside domain-trained models so
    any module can call get_registry().get_latest_model("yolov8n") instead of
    hard-coding a path.
    """
    from ml.registry.model_registry import get_registry
    registry = get_registry()
    return registry.register_model(
        model_name=name,
        version=version,
        path=str(path),
        classes=classes or [],
        framework=framework,
        extra={k: v for k, v in extra.items() if k not in ("classes", "framework")},
    )
