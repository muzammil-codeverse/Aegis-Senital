"""
Prepare video anomaly datasets for Phase 28 training/evaluation.

Scans raw UCF-Crime, XD-Violence, ShanghaiTech, Avenue, UCSD folders,
infers labels from folder names, normalizes them to canonical types,
then writes JSONL + metadata.csv to datasets/training/anomaly_video/.

Usage:
    python scripts/prepare_video_anomaly_dataset.py --all
    python scripts/prepare_video_anomaly_dataset.py --source ucf_crime
    python scripts/prepare_video_anomaly_dataset.py --all --clip-length 5 --stride 2.5
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "configs/evaluation/kaggle_anomaly_sources.yaml"
_OUT_DIR = Path("datasets/training/anomaly_video")
_VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv"}
_FRAME_EXTS = {".jpg", ".jpeg", ".png"}

LABEL_MAP: dict[str, str] = {
    # normal
    "normal": "normal",
    # violence
    "fighting": "violence", "fight": "violence", "assault": "violence",
    "abuse": "violence", "riot": "violence", "violence": "violence",
    # shooting
    "shooting": "shooting",
    # explosion/arson
    "explosion": "explosion", "arson": "explosion",
    # theft
    "burglary": "theft", "robbery": "theft", "shoplifting": "theft", "stealing": "theft",
    # traffic
    "roadaccidents": "traffic_accident", "road accident": "traffic_accident",
    # vandalism
    "vandalism": "vandalism",
    # arrest
    "arrest": "arrest",
    # generic
    "anomaly": "generic_anomaly", "abnormal": "generic_anomaly",
}

ANOMALY_TYPES = frozenset({
    "violence", "shooting", "explosion", "theft",
    "traffic_accident", "vandalism", "arrest", "generic_anomaly",
})


def _canonical_label(folder_name: str) -> str:
    key = folder_name.strip().lower().replace(" ", "").replace("_", "")
    for k, v in LABEL_MAP.items():
        if k.replace(" ", "").replace("_", "") == key:
            return v
    return "generic_anomaly"


def _collect_videos(raw_dir: Path) -> list[dict]:
    """Recursively find all video files, inferring label from parent folder."""
    items: list[dict] = []
    for path in raw_dir.rglob("*"):
        if path.suffix.lower() not in _VIDEO_EXTS:
            continue
        folder_label = path.parent.name
        label = _canonical_label(folder_label)
        is_anomaly = label != "normal"
        items.append({
            "video_path": str(path),
            "folder_label": folder_label,
            "label": label,
            "is_anomaly": is_anomaly,
        })
    return items


def _make_clips(
    video_items: list[dict],
    source_name: str,
    clip_length: float,
    stride: float,
) -> list[dict]:
    """Generate JSONL clip entries (no actual video splitting at this stage)."""
    clips: list[dict] = []
    for item in video_items:
        base = Path(item["video_path"]).stem
        start = 0.0
        clip_idx = 0
        while True:
            end = start + clip_length
            clip_id = f"{source_name}_{base}_{clip_idx:04d}"
            clips.append({
                "video_path": item["video_path"],
                "clip_id": clip_id,
                "label": item["label"],
                "is_anomaly": item["is_anomaly"],
                "start_sec": round(start, 2),
                "end_sec": round(end, 2),
                "source": source_name,
            })
            clip_idx += 1
            start += stride
            if start > 600.0:  # safety limit: don't generate infinite clips for unknown-length videos
                break
    return clips


def _load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        logger.error("Config not found: %s", _CONFIG_PATH)
        sys.exit(1)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    logger.info("Wrote %d records to %s", len(records), path)


def _write_csv(records: list[dict], path: Path) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(records[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    logger.info("Wrote metadata CSV: %s (%d rows)", path, len(records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare video anomaly training dataset")
    parser.add_argument("--all", action="store_true", help="Process all configured sources")
    parser.add_argument("--source", help="Process a single source by name")
    parser.add_argument("--clip-length", type=float, default=5.0, help="Clip length in seconds (default 5)")
    parser.add_argument("--stride", type=float, default=2.5, help="Clip stride in seconds (default 2.5)")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Train split ratio")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Val split ratio")
    args = parser.parse_args()

    if not args.all and not args.source:
        parser.print_help()
        sys.exit(0)

    config = _load_config()
    sources_to_process: dict[str, dict] = {}
    if args.all:
        sources_to_process = config
    else:
        if args.source not in config:
            logger.error("Unknown source: %s", args.source)
            sys.exit(1)
        sources_to_process = {args.source: config[args.source]}

    all_clips: list[dict] = []
    source_counts: dict[str, int] = {}

    for name, cfg in sources_to_process.items():
        raw_dir = Path(cfg.get("raw_dir", ""))
        if not raw_dir.exists():
            logger.warning("Raw dir not found for '%s': %s — skipping", name, raw_dir)
            continue
        logger.info("Scanning %s in %s ...", name, raw_dir)
        videos = _collect_videos(raw_dir)
        clips = _make_clips(videos, name, args.clip_length, args.stride)
        all_clips.extend(clips)
        source_counts[name] = len(clips)
        logger.info("  %d videos → %d clips", len(videos), len(clips))

    if not all_clips:
        logger.warning("No clips generated. Check that raw dataset directories are populated.")
        return

    random.shuffle(all_clips)
    n = len(all_clips)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    train = all_clips[:n_train]
    val = all_clips[n_train:n_train + n_val]
    test = all_clips[n_train + n_val:]

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(train, _OUT_DIR / "train.jsonl")
    _write_jsonl(val, _OUT_DIR / "val.jsonl")
    _write_jsonl(test, _OUT_DIR / "test.jsonl")
    _write_csv(all_clips, _OUT_DIR / "metadata.csv")

    label_dist: dict[str, int] = {}
    for c in all_clips:
        label_dist[c["label"]] = label_dist.get(c["label"], 0) + 1

    summary = {
        "total_clips": n,
        "train_clips": len(train),
        "val_clips": len(val),
        "test_clips": len(test),
        "clip_length_sec": args.clip_length,
        "stride_sec": args.stride,
        "label_distribution": label_dist,
        "source_clip_counts": source_counts,
    }
    with open(_OUT_DIR / "dataset_summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    logger.info("Dataset summary: %s", summary)
    logger.info("Output: %s", _OUT_DIR)


if __name__ == "__main__":
    main()
