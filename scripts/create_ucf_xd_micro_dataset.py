"""
Build UCF-Crime + XD-Violence micro supplement candidate datasets for VideoMAE training.

UCF-Crime is the base. XD-Violence contributes at most --max-xd-videos-per-class
video sequences per overlapping class. XD-Violence data is present as PNG frame
sequences in kaggle_zips/Train/<Category>/ directories (identified by *_x264_*.png).

Single-candidate usage:
    python scripts/create_ucf_xd_micro_dataset.py \\
      --ucf-dir datasets/training/anomaly_video_ucf_only \\
      --xd-raw-dir datasets/raw/anomaly/kaggle_zips \\
      --output-dir datasets/training/anomaly_video_ucf_plus_xd_micro \\
      --max-xd-videos-per-class 1

Multi-candidate intelligent selector usage:
    python scripts/create_ucf_xd_micro_dataset.py \\
      --ucf-dir datasets/training/anomaly_video_ucf_only \\
      --xd-raw-dir datasets/raw/anomaly/kaggle_zips \\
      --output-root datasets/training \\
      --candidate-video-counts 1 2 3 4 5 \\
      --max-training-hours 12 \\
      --target-training-hours 8 \\
      --observed-seconds-per-step 0.438 \\
      --batch-size 2 \\
      --epochs 5 \\
      --seed 42

Policy:
  - Hard cap per class: 4 videos (overridable via CLI).
  - If no candidate fits budget: fall back to UCF-only (exits with code 2).
  - XD supplement is added to train only — val/test remain UCF-only.
  - Never use full anomaly_video/train.jsonl without explicit audit.
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

# ---------------------------------------------------------------------------
# XD class -> UCF label mapping (safe overlapping classes only)
# ---------------------------------------------------------------------------
XD_TO_UCF_MAP: dict[str, str] = {
    "Fighting":     "violence",
    "Riot":         "violence",
    "Explosion":    "explosion",
    "Shooting":     "shooting",
    "RoadAccidents": "traffic_accident",
    "CarAccident":  "traffic_accident",
    "NormalVideos": "normal",
    "Normal":       "normal",
}

# Only these categories contain genuine XD-Violence PNG frame sequences
XD_PNG_CATEGORIES: set[str] = {
    "Fighting", "Explosion", "RoadAccidents", "Shooting", "NormalVideos",
}

HARD_CAP_SINGLE = 4      # hard cap for single-candidate (--max-xd-videos-per-class) mode
HARD_CAP_MULTI  = 5      # hard cap for multi-candidate (--candidate-video-counts) mode
DEFAULT_SPS = 0.75       # conservative seconds-per-step default
MAX_BUDGET_HOURS = 12.0  # never exceed this
TARGET_HOURS = 8.0


# ---------------------------------------------------------------------------
# Frame sequence helpers
# ---------------------------------------------------------------------------

def _find_xd_sequences(xd_raw_dir: Path, category: str) -> list[tuple[Path, str]]:
    """Return (frame_dir, prefix) for all *_x264_*.png video sequences in category."""
    cat_dir = xd_raw_dir / "Train" / category
    if not cat_dir.exists():
        return []
    prefixes: dict[str, Path] = {}
    for pf in cat_dir.glob("*_x264_*.png"):
        base = pf.stem                              # e.g. Fighting002_x264_0
        prefix = "_".join(base.rsplit("_", 1)[:-1]) # Fighting002_x264
        prefixes[prefix] = cat_dir
    return [(frame_dir, prefix) for prefix, frame_dir in sorted(prefixes.items())]


def _count_frames(frame_dir: Path, prefix: str) -> int:
    return len(glob.glob(str(frame_dir / f"{prefix}_*.png")))


def _make_xd_record(frame_dir: Path, prefix: str, label: str, clip_id: str) -> dict:
    return {
        "clip_type": "frames",
        "video_path": str(frame_dir),
        "frame_prefix": prefix,
        "frame_ext": ".png",
        "num_frames": _count_frames(frame_dir, prefix),
        "label": label,
        "is_anomaly": label != "normal",
        "source": "xd_violence",
        "clip_id": clip_id,
    }


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Runtime estimation
# ---------------------------------------------------------------------------

def _estimate_hours(train_clips: int, batch_size: int, epochs: int, sps: float) -> float:
    steps = math.ceil(train_clips / batch_size)
    return (steps * sps * epochs) / 3600.0


def _read_sps_from_log(log_path: Path) -> float | None:
    """Parse average seconds/step from an existing VideoMAE training log."""
    if not log_path.exists():
        return None
    epoch_times, clip_counts = [], []
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "done | train_loss" in line and "|" in line:
            parts = line.split("|")
            try:
                secs = float(parts[-1].strip().rstrip("s"))
                epoch_times.append(secs)
            except ValueError:
                pass
        if "clips=" in line:
            try:
                clip_counts.append(int(line.split("clips=")[-1].strip()))
            except ValueError:
                pass
    if epoch_times and clip_counts:
        avg_secs = sum(epoch_times) / len(epoch_times)
        clips = clip_counts[0]
        steps = math.ceil(clips / 2)
        return avg_secs / steps if steps > 0 else None
    return None


# ---------------------------------------------------------------------------
# Dataset builder for a single N-videos-per-class candidate
# ---------------------------------------------------------------------------

def _build_candidate(
    ucf_train: list[dict],
    ucf_val: list[dict],
    ucf_test: list[dict],
    xd_sequences_by_label: dict[str, list[tuple[Path, str]]],
    n_per_class: int,
    output_dir: Path,
    rng: random.Random,
    batch_size: int,
    epochs: int,
    sps: float,
) -> dict:
    """Build one candidate dataset and return its summary dict."""
    xd_clips: list[dict] = []
    xd_counts: dict[str, int] = {}
    for label, seqs in xd_sequences_by_label.items():
        chosen = seqs[:n_per_class]
        xd_counts[label] = len(chosen)
        for i, (frame_dir, prefix) in enumerate(chosen):
            xd_clips.append(_make_xd_record(
                frame_dir, prefix, label, f"xd_{prefix}_c{n_per_class}_clip_{i}"
            ))

    merged_train = ucf_train + xd_clips
    rng.shuffle(merged_train)

    est_hours = _estimate_hours(len(merged_train), batch_size, epochs, sps)

    all_records = merged_train + ucf_val + ucf_test
    src_counter   = Counter(r.get("source", "unknown") for r in all_records)
    label_counter = Counter(r.get("label", "unknown") for r in all_records)
    xd_in_train   = sum(1 for r in merged_train if r.get("source") == "xd_violence")

    summary = {
        "base_dataset": "ucf_crime",
        "supplement": "xd_violence_micro",
        "max_xd_videos_per_class": n_per_class,
        "selected_xd_videos_per_class": n_per_class,
        "xd_sequences_per_class": xd_counts,
        "train_clips": len(merged_train),
        "val_clips": len(ucf_val),
        "test_clips": len(ucf_test),
        "ucf_clips": len(ucf_train),
        "xd_clips": xd_in_train,
        "labels": dict(label_counter),
        "sources": dict(src_counter),
        "estimated_steps_per_epoch": math.ceil(len(merged_train) / batch_size),
        "estimated_epoch_minutes": round(_estimate_hours(len(merged_train), batch_size, 1, sps) * 60, 2),
        "estimated_total_training_hours": round(est_hours, 3),
        "batch_size": batch_size,
        "epochs": epochs,
        "seconds_per_step": round(sps, 4),
        "accepted_under_budget": est_hours <= MAX_BUDGET_HOURS,
        "budget_hours": MAX_BUDGET_HOURS,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(merged_train, output_dir / "train.jsonl")
    _write_jsonl(ucf_val,     output_dir / "val.jsonl")
    _write_jsonl(ucf_test,    output_dir / "test.jsonl")
    (output_dir / "dataset_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


# ---------------------------------------------------------------------------
# Intelligent multi-candidate selector
# ---------------------------------------------------------------------------

def select_best_candidate(
    summaries: list[tuple[int, dict, Path]],
    max_hours: float,
    target_hours: float,
) -> tuple[int, dict, Path] | None:
    """
    Pick the largest n-per-class candidate where est_hours <= max_hours.
    Among those, prefer the one closest to target_hours from below.
    """
    safe = [(n, s, p) for n, s, p in summaries if s["estimated_total_training_hours"] <= max_hours]
    if not safe:
        return None
    # Sort by estimated hours descending — pick largest safe
    safe.sort(key=lambda x: x[1]["estimated_total_training_hours"], reverse=True)
    return safe[0]


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def build_single(args: argparse.Namespace) -> None:
    """Build one dataset at --output-dir with --max-xd-videos-per-class."""
    rng = random.Random(args.seed)
    n = min(args.max_xd_videos_per_class, HARD_CAP_SINGLE)
    ucf_dir   = Path(args.ucf_dir)
    xd_dir    = Path(args.xd_raw_dir)
    output_dir = Path(args.output_dir)

    ucf_train = _load_jsonl(ucf_dir / "train.jsonl")
    ucf_val   = _load_jsonl(ucf_dir / "val.jsonl")
    ucf_test  = _load_jsonl(ucf_dir / "test.jsonl")

    sps = getattr(args, "observed_seconds_per_step", None) or DEFAULT_SPS
    log_sps = _read_sps_from_log(Path("logs/videomae_20ep.log"))
    if log_sps:
        sps = log_sps
    print(f"Seconds/step: {sps:.4f}")

    seqs_by_label: dict[str, list] = defaultdict(list)
    for cat in XD_PNG_CATEGORIES:
        label = XD_TO_UCF_MAP.get(cat)
        if not label:
            continue
        seqs = _find_xd_sequences(xd_dir, cat)
        rng.shuffle(seqs)
        seqs_by_label[label].extend(seqs[:n])

    # De-dup per label to exactly n
    deduped: dict[str, list] = {}
    for label, seqs in seqs_by_label.items():
        deduped[label] = seqs[:n]

    summary = _build_candidate(
        ucf_train, ucf_val, ucf_test, deduped,
        n, output_dir, rng,
        batch_size=getattr(args, "batch_size", 2),
        epochs=getattr(args, "epochs", 5),
        sps=sps,
    )
    print(json.dumps(summary, indent=2))
    if not summary["accepted_under_budget"]:
        print(f"WARNING: Estimated {summary['estimated_total_training_hours']:.2f}h exceeds budget.")
        sys.exit(2)


def build_multi(args: argparse.Namespace) -> None:
    """Build multiple candidate datasets and select the best safe one."""
    rng = random.Random(args.seed)
    ucf_dir    = Path(args.ucf_dir)
    xd_dir     = Path(args.xd_raw_dir)
    output_root = Path(args.output_root)
    max_hours   = getattr(args, "max_training_hours", MAX_BUDGET_HOURS)
    target_hrs  = getattr(args, "target_training_hours", TARGET_HOURS)

    # Determine seconds per step
    sps = getattr(args, "observed_seconds_per_step", None) or DEFAULT_SPS
    log_sps = _read_sps_from_log(Path("logs/videomae_20ep.log"))
    if log_sps and not getattr(args, "observed_seconds_per_step", None):
        sps = log_sps
    print(f"Seconds/step: {sps:.4f}  |  Budget: {max_hours}h  |  Target: {target_hrs}h")

    ucf_train = _load_jsonl(ucf_dir / "train.jsonl")
    ucf_val   = _load_jsonl(ucf_dir / "val.jsonl")
    ucf_test  = _load_jsonl(ucf_dir / "test.jsonl")
    print(f"UCF base: train={len(ucf_train)}, val={len(ucf_val)}, test={len(ucf_test)}")

    # Pre-discover all XD sequences (shuffle once for reproducibility)
    all_seqs_by_label: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for cat in sorted(XD_PNG_CATEGORIES):
        label = XD_TO_UCF_MAP.get(cat)
        if not label:
            continue
        seqs = _find_xd_sequences(xd_dir, cat)
        rng.shuffle(seqs)
        all_seqs_by_label[label].extend(seqs)
    # De-dup same prefix across categories mapping to same label
    for label in all_seqs_by_label:
        seen: set[str] = set()
        deduped = []
        for fd, pfx in all_seqs_by_label[label]:
            if pfx not in seen:
                seen.add(pfx)
                deduped.append((fd, pfx))
        all_seqs_by_label[label] = deduped

    print("\nAvailable XD sequences per label:")
    for label, seqs in sorted(all_seqs_by_label.items()):
        print(f"  {label}: {len(seqs)} sequences")

    counts = sorted(set(getattr(args, "candidate_video_counts", [1, 2, 3, 4, 5])))
    counts = [c for c in counts if 1 <= c <= HARD_CAP_MULTI]
    print(f"\nBuilding candidates for n_per_class={counts}...")

    candidate_rng = random.Random(args.seed)
    summaries: list[tuple[int, dict, Path]] = []

    for n in counts:
        # Take exactly n per label
        seqs_for_n: dict[str, list] = {
            label: seqs[:n] for label, seqs in all_seqs_by_label.items()
        }
        dir_name = f"anomaly_video_ucf_plus_xd_micro_{n}pc"
        out_dir = output_root / dir_name

        summary = _build_candidate(
            ucf_train, ucf_val, ucf_test, seqs_for_n,
            n, out_dir,
            random.Random(args.seed),  # deterministic per candidate
            batch_size=args.batch_size,
            epochs=args.epochs,
            sps=sps,
        )
        est = summary["estimated_total_training_hours"]
        ok  = summary["accepted_under_budget"]
        print(f"  n={n}: train={summary['train_clips']} clips, "
              f"xd={summary['xd_clips']}, est={est:.2f}h, "
              f"{'OK' if ok else 'OVER-BUDGET'}")
        summaries.append((n, summary, out_dir))

    # Also ensure the 1pc baseline exists
    best = select_best_candidate(summaries, max_hours, target_hrs)

    if best is None:
        print("\nWARNING: All candidates exceed budget. Falling back to UCF-only.")
        fallback_dir = ucf_dir
        selected_n, selected_summary, selected_dir = 0, {
            "train_clips": len(ucf_train),
            "val_clips":   len(ucf_val),
            "test_clips":  len(ucf_test),
            "xd_clips": 0,
            "estimated_total_training_hours": _estimate_hours(
                len(ucf_train), args.batch_size, args.epochs, sps),
            "accepted_under_budget": True,
            "selected_videos_per_class": 0,
        }, ucf_dir
    else:
        selected_n, selected_summary, selected_dir = best
        selected_summary["selected_videos_per_class"] = selected_n

    print(f"\n{'='*60}")
    print(f"SELECTED: n_per_class={selected_n}")
    print(f"  dataset:  {selected_dir}")
    print(f"  train:    {selected_summary['train_clips']} clips")
    print(f"  xd clips: {selected_summary.get('xd_clips', 0)}")
    print(f"  est. hrs: {selected_summary['estimated_total_training_hours']:.2f}h")
    print(f"  budget:   {max_hours}h")
    print(f"{'='*60}")

    # Write selection manifest
    manifest = {
        "phase": "28B_completion",
        "full_xd_training_allowed": False,
        "xd_micro_policy": {
            "candidate_video_counts": counts,
            "selected_videos_per_class": selected_n,
            "max_training_hours": max_hours,
            "target_training_hours": target_hrs,
            "selected_dataset": str(selected_dir),
            "estimated_training_hours": selected_summary["estimated_total_training_hours"],
        },
        "all_candidates": [
            {
                "n_per_class": n,
                "path": str(p),
                "train_clips": s["train_clips"],
                "xd_clips": s.get("xd_clips", 0),
                "estimated_hours": s["estimated_total_training_hours"],
                "accepted": s["accepted_under_budget"],
            }
            for n, s, p in summaries
        ],
    }
    manifest_path = output_root / "xd_micro_selection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest written: {manifest_path}")

    return selected_n, selected_dir, selected_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build UCF + XD micro supplement candidate datasets"
    )
    # Common
    parser.add_argument("--ucf-dir",  default="datasets/training/anomaly_video_ucf_only")
    parser.add_argument("--xd-raw-dir", default="datasets/raw/anomaly/kaggle_zips")
    parser.add_argument("--seed",  type=int, default=42)
    parser.add_argument("--clip-length",  type=int, default=16)
    parser.add_argument("--stride",       type=int, default=8)
    parser.add_argument("--sample-rate",  type=int, default=5)
    parser.add_argument("--batch-size",   type=int, default=2)
    parser.add_argument("--epochs",       type=int, default=5)
    parser.add_argument("--observed-seconds-per-step", type=float, default=None,
                        help="Observed seconds/step from prior training log")

    # Single-candidate mode
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (single-candidate mode)")
    parser.add_argument("--max-xd-videos-per-class", type=int, default=1)

    # Multi-candidate mode
    parser.add_argument("--output-root", default="datasets/training",
                        help="Root dir for all candidate subdirectories (multi mode)")
    parser.add_argument("--candidate-video-counts", type=int, nargs="+",
                        default=None, help="List of n_per_class values to try")
    parser.add_argument("--max-training-hours", type=float, default=MAX_BUDGET_HOURS)
    parser.add_argument("--target-training-hours", type=float, default=TARGET_HOURS)

    args = parser.parse_args()

    if args.candidate_video_counts is not None:
        # Multi-candidate mode
        build_multi(args)
    else:
        # Single-candidate mode (backward compatible)
        if args.output_dir is None:
            args.output_dir = "datasets/training/anomaly_video_ucf_plus_xd_micro"
        build_single(args)


if __name__ == "__main__":
    main()
