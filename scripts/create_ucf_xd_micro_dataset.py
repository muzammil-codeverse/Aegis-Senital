"""
Build a UCF-Crime + XD-Violence micro supplement dataset for VideoMAE training.

UCF-Crime is the base. XD-Violence contributes at most --max-xd-videos-per-class
video sequences per overlapping class. XD-Violence data is present as PNG frame
sequences in kaggle_zips/Train/<Category>/ directories.

Usage:
    python scripts/create_ucf_xd_micro_dataset.py \\
      --ucf-dir datasets/training/anomaly_video_ucf_only \\
      --xd-raw-dir datasets/raw/anomaly/kaggle_zips \\
      --output-dir datasets/training/anomaly_video_ucf_plus_xd_micro \\
      --max-xd-videos-per-class 1 \\
      --clip-length 16 --stride 8 --sample-rate 5 --seed 42

Policy:
  - Hard cap: never exceed 4 XD videos per class.
  - Default: 1 video per class.
  - If estimated training time > 10h, auto-reduce to UCF-only and report.
  - Do not restart completed UCF training.
  - XD is a generalization supplement only — not used for acceptance claims.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

# XD category directories → UCF label mapping
# Only classes that safely overlap between UCF-Crime and XD-Violence.
XD_TO_UCF_MAP: dict[str, str] = {
    # XD folder name       → UCF label
    "Fighting":            "violence",
    "Riot":                "violence",
    "Explosion":           "explosion",
    "Shooting":            "shooting",
    "RoadAccidents":       "traffic_accident",
    "CarAccident":         "traffic_accident",
    "NormalVideos":        "normal",
    "Normal":              "normal",
}

# PNG frame-sequence categories (XD-Violence origin, identified by *_x264_*.png pattern)
XD_PNG_CATEGORIES = {
    "Fighting", "Explosion", "RoadAccidents", "Shooting", "NormalVideos",
}

HARD_CAP = 4  # Never exceed this regardless of CLI argument

# Conservative seconds-per-step baseline (overridden if log is readable)
DEFAULT_SECONDS_PER_STEP = 0.75

BUDGET_HOURS = 10.0


def _find_xd_sequences(xd_raw_dir: Path, category: str) -> list[tuple[Path, str]]:
    """Return list of (frame_dir, prefix) for all XD PNG sequences in a category."""
    cat_dir = xd_raw_dir / "Train" / category
    if not cat_dir.exists():
        return []
    # XD frames: <Category><NNN>_x264_<frame>.png — identify unique video prefixes
    png_files = list(cat_dir.glob("*_x264_*.png"))
    prefixes: dict[str, Path] = {}
    for pf in png_files:
        # e.g. Fighting002_x264_0.png → prefix = Fighting002_x264
        base = pf.stem  # Fighting002_x264_0
        prefix = "_".join(base.rsplit("_", 1)[:-1])  # Fighting002_x264
        prefixes[prefix] = cat_dir
    return [(frame_dir, prefix) for prefix, frame_dir in sorted(prefixes.items())]


def _count_frames(frame_dir: Path, prefix: str) -> int:
    pattern = str(frame_dir / f"{prefix}_*.png")
    return len(glob.glob(pattern))


def _make_xd_record(
    frame_dir: Path,
    prefix: str,
    label: str,
    clip_id: str,
) -> dict:
    n_frames = _count_frames(frame_dir, prefix)
    return {
        "clip_type": "frames",
        "video_path": str(frame_dir),
        "frame_prefix": prefix,
        "frame_ext": ".png",
        "num_frames": n_frames,
        "label": label,
        "is_anomaly": label != "normal",
        "source": "xd_violence",
        "clip_id": clip_id,
    }


def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _estimate_runtime(
    train_clips: int,
    batch_size: int,
    remaining_epochs: int,
    seconds_per_step: float,
) -> float:
    steps_per_epoch = math.ceil(train_clips / batch_size)
    epoch_minutes = steps_per_epoch * seconds_per_step / 60
    total_hours = epoch_minutes * remaining_epochs / 60
    return total_hours


def _read_seconds_per_step_from_log(log_path: Path) -> float | None:
    """Parse observed seconds/step from videomae training log."""
    if not log_path.exists():
        return None
    epoch_times = []
    clip_counts = []
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        # INFO  Epoch 6 done | train_loss=0.3454 | 167.1s
        if "done | train_loss" in line and "s" in line.split("|")[-1]:
            try:
                secs = float(line.split("|")[-1].strip().rstrip("s"))
                epoch_times.append(secs)
            except ValueError:
                pass
        # INFO  Training — epochs=20 batch=2 fp16=True device=cuda clips=452
        if "clips=" in line:
            try:
                clips = int(line.split("clips=")[-1].strip())
                clip_counts.append(clips)
            except ValueError:
                pass
    if epoch_times and clip_counts:
        avg_epoch_sec = sum(epoch_times) / len(epoch_times)
        clips = clip_counts[0]
        steps = math.ceil(clips / 2)  # assume batch=2
        return avg_epoch_sec / steps if steps > 0 else None
    return None


def build(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    max_per_class = min(args.max_xd_videos_per_class, HARD_CAP)
    if max_per_class != args.max_xd_videos_per_class:
        print(f"WARNING: --max-xd-videos-per-class capped at hard limit {HARD_CAP}")

    ucf_dir = Path(args.ucf_dir)
    xd_raw_dir = Path(args.xd_raw_dir)
    output_dir = Path(args.output_dir)

    # -- Load UCF base splits -----------------------------------------------
    print(f"\nLoading UCF base from: {ucf_dir}")
    ucf_train = _load_jsonl(ucf_dir / "train.jsonl")
    ucf_val   = _load_jsonl(ucf_dir / "val.jsonl")
    ucf_test  = _load_jsonl(ucf_dir / "test.jsonl")
    print(f"UCF base: train={len(ucf_train)}, val={len(ucf_val)}, test={len(ucf_test)}")

    # -- Discover XD sequences -----------------------------------------------
    print(f"\nScanning XD sequences in: {xd_raw_dir}")
    xd_clips_by_label: dict[str, list[dict]] = defaultdict(list)

    for category, ucf_label in XD_TO_UCF_MAP.items():
        if category not in XD_PNG_CATEGORIES:
            continue  # skip MP4 categories (those are UCF-Crime clips, not XD)
        sequences = _find_xd_sequences(xd_raw_dir, category)
        print(f"  {category} -> {ucf_label}: {len(sequences)} XD sequences found")
        if not sequences:
            continue
        rng.shuffle(sequences)
        chosen = sequences[:max_per_class]
        for i, (frame_dir, prefix) in enumerate(chosen):
            n = _count_frames(frame_dir, prefix)
            clip_id = f"xd_{prefix}_clip_{i}"
            rec = _make_xd_record(frame_dir, prefix, ucf_label, clip_id)
            print(f"    Selected: {prefix} ({n} frames) → {clip_id}")
            xd_clips_by_label[ucf_label].append(rec)

    total_xd = sum(len(v) for v in xd_clips_by_label.values())
    print(f"\nTotal XD clips selected: {total_xd}")
    if total_xd == 0:
        print("WARNING: No XD sequences found. Output will be identical to UCF-only.")

    # -- Build merged splits -------------------------------------------------
    # Add XD clips only to train (not val/test — XD is supplement, not evaluation)
    xd_all = [rec for clips in xd_clips_by_label.values() for rec in clips]
    merged_train = ucf_train + xd_all
    rng.shuffle(merged_train)
    merged_val  = ucf_val   # val remains UCF-only
    merged_test = ucf_test  # test remains UCF-only

    print(f"\nMerged: train={len(merged_train)}, val={len(merged_val)}, test={len(merged_test)}")

    # -- Runtime budget guard -----------------------------------------------
    log_path = Path("logs/videomae_20ep.log")
    observed_sps = _read_seconds_per_step_from_log(log_path)
    sps = observed_sps if observed_sps else DEFAULT_SECONDS_PER_STEP
    print(f"\nObserved seconds/step: {sps:.3f}s" + (" (from log)" if observed_sps else " (default estimate)"))

    # Estimate for remaining epochs (assume ~15 epochs remaining by default)
    remaining_epochs = max(1, args.remaining_epochs)
    batch_size = args.batch_size
    est_hours = _estimate_runtime(len(merged_train), batch_size, remaining_epochs, sps)
    print(f"Estimated training: {len(merged_train)} clips × {remaining_epochs} epochs "
          f"@ batch={batch_size} → {est_hours:.2f}h")

    accepted = True
    if est_hours > BUDGET_HOURS:
        print(f"WARNING: Estimated {est_hours:.1f}h exceeds {BUDGET_HOURS}h budget!")
        if total_xd > 0 and max_per_class > 1:
            print("Reducing XD supplement to 1 video/class...")
            # Rebuild with 1 per class
            reduced_xd: list[dict] = []
            for label, clips in xd_clips_by_label.items():
                reduced_xd.extend(clips[:1])
            merged_train = ucf_train + reduced_xd
            rng.shuffle(merged_train)
            est_hours = _estimate_runtime(len(merged_train), batch_size, remaining_epochs, sps)
            print(f"Reduced: {len(merged_train)} clips → {est_hours:.2f}h")
        if est_hours > BUDGET_HOURS:
            print(f"ERROR: Even with reduction, estimated {est_hours:.1f}h > {BUDGET_HOURS}h budget.")
            print("Falling back to UCF-only (identical to anomaly_video_ucf_only).")
            merged_train = ucf_train
            rng.shuffle(merged_train)
            xd_all = []
            total_xd = 0
            est_hours = _estimate_runtime(len(merged_train), batch_size, remaining_epochs, sps)
            accepted = False

    # -- Write output -------------------------------------------------------
    print(f"\nWriting to: {output_dir}")
    _write_jsonl(merged_train, output_dir / "train.jsonl")
    _write_jsonl(merged_val,   output_dir / "val.jsonl")
    _write_jsonl(merged_test,  output_dir / "test.jsonl")

    # Count sources and labels
    all_records = merged_train + merged_val + merged_test
    sources_counter = Counter(r.get("source", "unknown") for r in all_records)
    labels_counter  = Counter(r.get("label", "unknown") for r in all_records)
    xd_in_train = sum(1 for r in merged_train if r.get("source") == "xd_violence")

    summary = {
        "base": "ucf_crime",
        "xd_policy": "micro_supplement" if accepted and total_xd > 0 else "ucf_only_fallback",
        "max_xd_videos_per_class": max_per_class,
        "xd_sequences_per_class": {
            label: len(clips) for label, clips in xd_clips_by_label.items()
        },
        "train_clips": len(merged_train),
        "val_clips": len(merged_val),
        "test_clips": len(merged_test),
        "xd_clips_in_train": xd_in_train,
        "ucf_clips_in_train": len(merged_train) - xd_in_train,
        "estimated_total_training_hours": round(est_hours, 2),
        "budget_hours": BUDGET_HOURS,
        "budget_accepted": accepted,
        "remaining_epochs": remaining_epochs,
        "batch_size": batch_size,
        "seconds_per_step": round(sps, 4),
        "labels": dict(labels_counter),
        "sources": dict(sources_counter),
    }
    (output_dir / "dataset_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(f"\nDataset written to: {output_dir}")
    if not accepted:
        print("WARNING: Budget exceeded — output is UCF-only (no XD supplement added).")
        sys.exit(2)  # Non-zero exit but not crash so callers can detect fallback


def main() -> None:
    parser = argparse.ArgumentParser(description="Build UCF + XD micro supplement dataset")
    parser.add_argument("--ucf-dir",  default="datasets/training/anomaly_video_ucf_only",
                        help="Path to UCF-only base JSONL directory")
    parser.add_argument("--xd-raw-dir", default="datasets/raw/anomaly/kaggle_zips",
                        help="Path to XD-Violence raw directory (containing Train/<Category>/)")
    parser.add_argument("--output-dir", default="datasets/training/anomaly_video_ucf_plus_xd_micro",
                        help="Output directory for merged JSONL")
    parser.add_argument("--max-xd-videos-per-class", type=int, default=1,
                        help=f"Max XD video sequences per class (hard cap {HARD_CAP})")
    parser.add_argument("--clip-length", type=int, default=16)
    parser.add_argument("--stride",      type=int, default=8)
    parser.add_argument("--sample-rate", type=int, default=5)
    parser.add_argument("--seed",        type=int, default=42)
    parser.add_argument("--batch-size",  type=int, default=2,
                        help="Training batch size for runtime estimate")
    parser.add_argument("--remaining-epochs", type=int, default=15,
                        help="Remaining training epochs for budget estimate")
    args = parser.parse_args()
    build(args)


if __name__ == "__main__":
    main()
