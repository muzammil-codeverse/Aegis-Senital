"""
Download and cache pretrained video/anomaly models for Phase 28.

Usage:
    python scripts/download_pretrained_anomaly_models.py --models videomae_kinetics
    python scripts/download_pretrained_anomaly_models.py --models videomae_ucf_crime videomae_kinetics
    python scripts/download_pretrained_anomaly_models.py --models slowfast_r50 --device cuda
    python scripts/download_pretrained_anomaly_models.py --all --device cuda

GPU check is performed before any model caching.
Models are cached locally; no internet required after first download.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_OUT_DIR = Path("models/anomaly/pretrained")
_MANIFEST_PATH = Path("models/anomaly/pretrained_manifest.json")

MODEL_REGISTRY = {
    "videomae_ucf_crime": {
        "source": "huggingface",
        "repo_id": "OPear/videomae-large-finetuned-UCF-Crime",
        "type": "video_classification",
        "description": "VideoMAE-Large fine-tuned on UCF-Crime (anomaly classification baseline)",
        "local_dir": "models/anomaly/pretrained/videomae_ucf_crime",
    },
    "videomae_kinetics": {
        "source": "huggingface",
        "repo_id": "MCG-NJU/videomae-base-finetuned-kinetics",
        "type": "video_classification",
        "description": "VideoMAE-Base fine-tuned on Kinetics (action recognition backbone)",
        "local_dir": "models/anomaly/pretrained/videomae_kinetics",
    },
    "slowfast_r50": {
        "source": "torchhub",
        "repo": "facebookresearch/pytorchvideo",
        "model": "slowfast_r50",
        "description": "SlowFast R50 pretrained on Kinetics-400 (action recognition baseline)",
        "local_dir": "models/anomaly/pretrained/slowfast_r50",
        "checkpoint_file": "models/anomaly/pretrained/slowfast_r50/slowfast_r50.pt",
    },
}


def _check_gpu(device: str) -> None:
    try:
        import torch
        if device.startswith("cuda") and not torch.cuda.is_available():
            logger.error(
                "CUDA not available. torch.cuda.is_available() = False.\n"
                "Fix PyTorch CUDA: pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )
            sys.exit(1)
        if torch.cuda.is_available():
            logger.info("GPU: %s | VRAM: %.1f GB", torch.cuda.get_device_name(0),
                        torch.cuda.get_device_properties(0).total_memory / 1e9)
    except ImportError:
        logger.error("torch not installed.")
        sys.exit(1)


def _download_huggingface(name: str, cfg: dict, continue_on_error: bool) -> dict:
    """Cache a Hugging Face model locally using snapshot_download."""
    repo_id = cfg["repo_id"]
    local_dir = cfg["local_dir"]
    entry = {"name": name, "status": "pending", "local_dir": local_dir, "error": None}
    try:
        from huggingface_hub import snapshot_download
        logger.info("[%s] Downloading from HuggingFace: %s → %s", name, repo_id, local_dir)
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        snapshot_download(repo_id=repo_id, local_dir=local_dir, ignore_patterns=["*.msgpack", "flax_model*"])
        elapsed = time.time() - t0
        logger.info("[%s] Downloaded in %.1fs → %s", name, elapsed, local_dir)
        entry["status"] = "success"
    except Exception as exc:
        logger.error("[%s] HuggingFace download failed: %s", name, exc)
        entry["status"] = "failed"
        entry["error"] = str(exc)
        if not continue_on_error:
            sys.exit(1)
    return entry


def _download_torchhub(name: str, cfg: dict, device: str, continue_on_error: bool) -> dict:
    """Cache a PyTorchVideo Torch Hub model."""
    repo = cfg["repo"]
    model_name = cfg["model"]
    local_dir = cfg["local_dir"]
    checkpoint_file = cfg.get("checkpoint_file", f"{local_dir}/{model_name}.pt")
    entry = {"name": name, "status": "pending", "local_dir": local_dir, "error": None}
    try:
        import torch
        logger.info("[%s] Loading from Torch Hub: %s/%s", name, repo, model_name)
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        model = torch.hub.load(repo, model_name, pretrained=True)
        model.eval()
        torch.save({"model_state_dict": model.state_dict()}, checkpoint_file)
        elapsed = time.time() - t0
        logger.info("[%s] Saved checkpoint in %.1fs → %s", name, elapsed, checkpoint_file)
        entry["status"] = "success"
        entry["checkpoint_file"] = checkpoint_file
    except Exception as exc:
        logger.error("[%s] Torch Hub download failed: %s", name, exc)
        entry["status"] = "failed"
        entry["error"] = str(exc)
        if not continue_on_error:
            sys.exit(1)
    return entry


def _load_manifest() -> dict:
    if _MANIFEST_PATH.exists():
        with open(_MANIFEST_PATH) as fh:
            return json.load(fh)
    return {}


def _save_manifest(manifest: dict) -> None:
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MANIFEST_PATH, "w") as fh:
        json.dump(manifest, fh, indent=2)
    logger.info("Manifest written: %s", _MANIFEST_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download pretrained anomaly models")
    parser.add_argument("--models", nargs="+", choices=list(MODEL_REGISTRY.keys()),
                        help="Models to download")
    parser.add_argument("--all", action="store_true", help="Download all models")
    parser.add_argument("--device", default="cuda", help="Device (cuda/cpu)")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    if not args.models and not args.all:
        parser.print_help()
        sys.exit(0)

    _check_gpu(args.device)

    targets = list(MODEL_REGISTRY.keys()) if args.all else (args.models or [])
    manifest = _load_manifest()

    for name in targets:
        cfg = MODEL_REGISTRY[name]
        logger.info("=== %s: %s ===", name, cfg["description"])

        local_dir = Path(cfg["local_dir"])
        if local_dir.exists() and any(local_dir.iterdir()):
            logger.info("[%s] Already cached at %s — skipping (delete dir to re-download)", name, local_dir)
            manifest[name] = manifest.get(name, {})
            manifest[name]["status"] = "cached"
            manifest[name]["local_dir"] = str(local_dir)
            continue

        if cfg["source"] == "huggingface":
            entry = _download_huggingface(name, cfg, args.continue_on_error)
        elif cfg["source"] == "torchhub":
            entry = _download_torchhub(name, cfg, args.device, args.continue_on_error)
        else:
            logger.warning("[%s] Unknown source: %s", name, cfg["source"])
            entry = {"name": name, "status": "skipped", "error": "unknown source"}

        manifest[name] = entry

    _save_manifest(manifest)

    failed = [n for n, e in manifest.items() if e.get("status") == "failed"]
    if failed:
        logger.warning("Failed downloads: %s", failed)
    else:
        logger.info("All requested models cached.")


if __name__ == "__main__":
    main()
