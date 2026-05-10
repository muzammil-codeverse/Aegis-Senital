"""
Download Roboflow anomaly datasets for Phase 28.

Usage:
    python scripts/download_roboflow_anomaly_datasets.py --list-sources
    python scripts/download_roboflow_anomaly_datasets.py --source violence_detection_cctv --continue-on-error

Token: set ROBOFLOW_API_KEY in the environment.
NEVER hard-code the key.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "configs/evaluation/roboflow_anomaly_sources.yaml"
_MANIFEST_PATH = "datasets/raw/anomaly/roboflow_download_manifest.json"


def _load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        logger.error("Config not found: %s", _CONFIG_PATH)
        sys.exit(1)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _get_api_key() -> str | None:
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        logger.error(
            "ROBOFLOW_API_KEY not set in environment.\n"
            "  Windows PowerShell: $env:ROBOFLOW_API_KEY='YOUR_KEY'\n"
            "  Linux/macOS: export ROBOFLOW_API_KEY=YOUR_KEY"
        )
        return None
    return key


def _download_source(name: str, cfg: dict, api_key: str, continue_on_error: bool) -> dict:
    workspace = cfg.get("workspace", "")
    project = cfg.get("project", "")
    version = cfg.get("version")
    fmt = cfg.get("format", "yolov8")
    raw_dir = cfg.get("raw_dir", f"datasets/raw/anomaly/{name}")

    entry: dict = {
        "name": name,
        "status": "pending",
        "raw_dir": raw_dir,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    try:
        from roboflow import Roboflow
    except ImportError:
        msg = "roboflow package not installed. Install with: pip install roboflow"
        logger.error(msg)
        entry["status"] = "failed"
        entry["error"] = msg
        if not continue_on_error:
            sys.exit(1)
        return entry

    try:
        rf = Roboflow(api_key=api_key)
        ws = rf.workspace(workspace)
        proj = ws.project(project)

        if version is not None:
            ver = proj.version(int(version))
        else:
            versions = proj.versions()
            if not versions:
                raise RuntimeError(f"No versions found for project '{project}'")
            ver = versions[-1]

        logger.info("Downloading %s/%s (version %s, format %s) → %s", workspace, project, ver.version, fmt, raw_dir)
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        dataset = ver.download(fmt, location=raw_dir, overwrite=True)
        logger.info("Downloaded: %s", dataset.location)

        entry["status"] = "success"
        entry["version"] = ver.version
    except Exception as exc:
        logger.error("Download failed for '%s': %s", name, exc)
        entry["status"] = "failed"
        entry["error"] = str(exc)
        if not continue_on_error:
            sys.exit(1)

    return entry


def _load_manifest() -> dict:
    if os.path.exists(_MANIFEST_PATH):
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_manifest(manifest: dict) -> None:
    Path(_MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(_MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    logger.info("Manifest written: %s", _MANIFEST_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Roboflow anomaly datasets")
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--source", help="Source name from config")
    parser.add_argument("--all", action="store_true", help="Download all sources")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    config = _load_config()

    if args.list_sources:
        print("\nConfigured Roboflow anomaly sources:")
        for name, cfg in config.items():
            print(f"  {name}")
            print(f"    workspace: {cfg.get('workspace')}")
            print(f"    project:   {cfg.get('project')}")
            print(f"    role:      {cfg.get('role')}")
        return

    if not args.source and not args.all:
        parser.print_help()
        sys.exit(0)

    api_key = _get_api_key()
    if not api_key:
        sys.exit(1)

    manifest = _load_manifest()
    targets: dict[str, dict] = {}
    if args.all:
        targets = config
    elif args.source:
        if args.source not in config:
            logger.error("Unknown source '%s'. Use --list-sources.", args.source)
            sys.exit(1)
        targets = {args.source: config[args.source]}

    for name, cfg in targets.items():
        logger.info("=== %s ===", name)
        entry = _download_source(name, cfg, api_key, args.continue_on_error)
        manifest[name] = entry

    _save_manifest(manifest)


if __name__ == "__main__":
    main()
