"""
Download Kaggle anomaly datasets for Phase 28.

Usage:
    python scripts/download_kaggle_anomaly_datasets.py --list-sources
    python scripts/download_kaggle_anomaly_datasets.py --source ucf_crime --continue-on-error
    python scripts/download_kaggle_anomaly_datasets.py --source xd_violence --continue-on-error
    python scripts/download_kaggle_anomaly_datasets.py --all --continue-on-error

Token: set KAGGLE_API_TOKEN in the environment or write it to ~/.kaggle/access_token.
NEVER hard-code the token.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "configs/evaluation/kaggle_anomaly_sources.yaml"
_MANIFEST_PATH = "datasets/raw/anomaly/download_manifest.json"


def _load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        logger.error("Config not found: %s", _CONFIG_PATH)
        sys.exit(1)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _resolve_token() -> bool:
    """Configure Kaggle credentials from environment or ~/.kaggle/access_token.
    Returns True if credentials are available."""
    token = os.environ.get("KAGGLE_API_TOKEN", "").strip()
    if token:
        kaggle_dir = Path.home() / ".kaggle"
        kaggle_dir.mkdir(parents=True, exist_ok=True)
        token_file = kaggle_dir / "access_token"
        token_file.write_text(token)
        try:
            token_file.chmod(0o600)
        except Exception:
            pass
        logger.info("Kaggle token resolved from KAGGLE_API_TOKEN environment variable.")
        return True

    token_file = Path.home() / ".kaggle" / "access_token"
    if token_file.exists():
        logger.info("Kaggle token found at %s", token_file)
        return True

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        logger.info("Kaggle credentials found at %s", kaggle_json)
        return True

    logger.error(
        "No Kaggle credentials found.\n"
        "  Option 1: set KAGGLE_API_TOKEN environment variable\n"
        "  Option 2: write token to ~/.kaggle/access_token\n"
        "  Option 3: place kaggle.json in ~/.kaggle/"
    )
    return False


def _download_dataset(slug: str, zip_dir: str, force: bool = False) -> bool:
    """Shell out to kaggle CLI to download a dataset. Returns True on success."""
    Path(zip_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "kaggle",
        "datasets", "download",
        "-d", slug,
        "-p", zip_dir,
        "--unzip",
    ]
    if force:
        cmd.append("--force")

    logger.info("Downloading dataset: %s → %s", slug, zip_dir)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            logger.error("kaggle CLI failed for '%s':\n%s", slug, result.stderr[:500])
            return False
        logger.info("Download complete: %s", slug)
        return True
    except FileNotFoundError:
        logger.error(
            "kaggle CLI not found. Install with: pip install kaggle\n"
            "Then retry."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error("Download timed out for %s", slug)
        return False
    except Exception as exc:
        logger.error("Unexpected error downloading %s: %s", slug, exc)
        return False


def _load_manifest() -> dict:
    if os.path.exists(_MANIFEST_PATH):
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_manifest(manifest: dict) -> None:
    Path(_MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(_MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    logger.info("Manifest written to %s", _MANIFEST_PATH)


def download_source(name: str, cfg: dict, force: bool, continue_on_error: bool) -> dict:
    zip_dir = cfg.get("zip_dir", f"datasets/raw/anomaly/kaggle_zips")
    primary_slug = cfg.get("kaggle_slug", "")
    fallback_slug = cfg.get("fallback_slug", "")

    entry: dict = {
        "name": name,
        "status": "pending",
        "slug_used": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    success = _download_dataset(primary_slug, zip_dir, force=force)
    if success:
        entry["status"] = "success"
        entry["slug_used"] = primary_slug
        return entry

    if fallback_slug:
        logger.info("Primary slug failed, trying fallback: %s", fallback_slug)
        success = _download_dataset(fallback_slug, zip_dir, force=force)
        if success:
            entry["status"] = "success"
            entry["slug_used"] = fallback_slug
            return entry

    entry["status"] = "failed"
    entry["error"] = f"Both slugs failed: {primary_slug} / {fallback_slug}"
    if not continue_on_error:
        logger.error("Download failed for '%s'. Use --continue-on-error to skip.", name)
        sys.exit(1)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Kaggle anomaly datasets")
    parser.add_argument("--list-sources", action="store_true", help="List configured sources")
    parser.add_argument("--source", help="Download a specific source by name")
    parser.add_argument("--all", action="store_true", help="Download all configured sources")
    parser.add_argument("--continue-on-error", action="store_true", help="Skip failed downloads")
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    args = parser.parse_args()

    config = _load_config()

    if args.list_sources:
        print("\nConfigured Kaggle anomaly sources:")
        for name, cfg in config.items():
            req = " [REQUIRED]" if cfg.get("required") else ""
            print(f"  {name}{req}")
            print(f"    slug:    {cfg.get('kaggle_slug')}")
            print(f"    role:    {cfg.get('role')}")
            print(f"    raw_dir: {cfg.get('raw_dir')}")
        return

    if not args.source and not args.all:
        parser.print_help()
        sys.exit(0)

    if not _resolve_token():
        sys.exit(1)

    manifest = _load_manifest()
    targets: dict[str, dict] = {}
    if args.all:
        targets = config
    elif args.source:
        if args.source not in config:
            logger.error("Unknown source '%s'. Use --list-sources to see options.", args.source)
            sys.exit(1)
        targets = {args.source: config[args.source]}

    for name, cfg in targets.items():
        logger.info("=== %s ===", name)
        entry = download_source(name, cfg, force=args.force, continue_on_error=args.continue_on_error)
        manifest[name] = entry

    _save_manifest(manifest)

    failed = [n for n, e in manifest.items() if e.get("status") == "failed"]
    if failed:
        logger.warning("Failed downloads: %s", failed)
        if not args.continue_on_error:
            sys.exit(1)
    else:
        logger.info("All requested downloads complete.")


if __name__ == "__main__":
    main()
