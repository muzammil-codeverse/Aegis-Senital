"""
Extract downloaded Kaggle anomaly dataset zips.

Usage:
    python scripts/extract_anomaly_dataset_zips.py --all
    python scripts/extract_anomaly_dataset_zips.py --source ucf_crime --force
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "configs/evaluation/kaggle_anomaly_sources.yaml"
_MANIFEST_PATH = "datasets/raw/anomaly/extraction_manifest.json"
_ZIP_DIR = "datasets/raw/anomaly/kaggle_zips"

_SLUG_TO_NAME: dict[str, str] = {
    "ucf-crime-dataset": "ucf_crime",
    "ucf-crimes": "ucf_crime",
    "xd-violence": "xd_violence",
    "xd-violence-video-dataset": "xd_violence",
    "shanghaitech-anomaly-detection": "shanghaitech",
    "avenue": "avenue",
    "ucsd-anomaly-dataset": "ucsd",
}


def _load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        logger.error("Config not found: %s", _CONFIG_PATH)
        sys.exit(1)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _find_zips() -> list[Path]:
    base = Path(_ZIP_DIR)
    if not base.exists():
        logger.warning("Zip directory not found: %s", _ZIP_DIR)
        return []
    return list(base.glob("*.zip")) + list(base.glob("**/*.zip"))


def _match_zip_to_source(zip_path: Path, config: dict) -> tuple[str, dict] | None:
    stem = zip_path.stem.lower()
    # Direct match
    if stem in config:
        return stem, config[stem]
    # Slug-based match
    name = _SLUG_TO_NAME.get(stem)
    if name and name in config:
        return name, config[name]
    # Fuzzy match by substring
    for name, cfg in config.items():
        slug = cfg.get("kaggle_slug", "").split("/")[-1].lower()
        if slug in stem or stem in slug:
            return name, cfg
    return None


def _extract_zip(zip_path: Path, dest_dir: str, force: bool = False) -> bool:
    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()) and not force:
        logger.info("Already extracted (use --force to re-extract): %s", dest_dir)
        return True
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            logger.info("Extracting %d files from %s → %s", len(members), zip_path.name, dest_dir)
            zf.extractall(dest)
        return True
    except zipfile.BadZipFile:
        logger.error("Bad zip file: %s", zip_path)
        return False
    except Exception as exc:
        logger.error("Extraction error for %s: %s", zip_path, exc)
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
    logger.info("Extraction manifest written: %s", _MANIFEST_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Kaggle anomaly dataset zips")
    parser.add_argument("--all", action="store_true", help="Extract all zips in the zip directory")
    parser.add_argument("--source", help="Extract a specific source by name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing extractions")
    args = parser.parse_args()

    if not args.all and not args.source:
        parser.print_help()
        sys.exit(0)

    config = _load_config()
    manifest = _load_manifest()
    zips = _find_zips()

    if not zips:
        logger.warning("No zip files found in %s", _ZIP_DIR)
        logger.info("Place downloaded zips there and re-run, or use download_kaggle_anomaly_datasets.py")
        return

    if args.source:
        if args.source not in config:
            logger.error("Unknown source '%s'", args.source)
            sys.exit(1)
        target_cfg = config[args.source]
        target_zips = [z for z in zips if _match_zip_to_source(z, config) and
                       _match_zip_to_source(z, config)[0] == args.source]
        if not target_zips:
            logger.warning("No zip found for source '%s' in %s", args.source, _ZIP_DIR)
            return
        process_pairs = [(args.source, target_cfg, z) for z in target_zips]
    else:
        process_pairs = []
        for zip_path in zips:
            match = _match_zip_to_source(zip_path, config)
            if match:
                name, cfg = match
                process_pairs.append((name, cfg, zip_path))
            else:
                logger.warning("Could not match zip to source: %s — skipping", zip_path.name)

    for name, cfg, zip_path in process_pairs:
        dest_dir = cfg.get("raw_dir", f"datasets/raw/anomaly/{name}")
        success = _extract_zip(zip_path, dest_dir, force=args.force)
        manifest[name] = {
            "source": name,
            "zip_file": str(zip_path),
            "dest_dir": dest_dir,
            "status": "success" if success else "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    _save_manifest(manifest)


if __name__ == "__main__":
    main()
