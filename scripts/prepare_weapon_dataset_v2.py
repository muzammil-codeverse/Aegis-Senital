"""Merge and remap multiple raw weapon Roboflow sources into a single taxonomy-v2 dataset.

Reads:
  configs/taxonomy/weapon_taxonomy_v2.yaml  — canonical classes, aliases, coverage thresholds
  datasets/raw/weapon/*/                    — each downloaded source (YOLOv8 format)

Writes:
  datasets/training/weapon_v2/              — merged train/val/test for YOLO training
  datasets/evaluation/weapon_v2/            — merged val+test as flat eval dataset
  datasets/training/weapon_v2/prep_report.json

Usage:
  python scripts/prepare_weapon_dataset_v2.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = REPO_ROOT / "configs" / "taxonomy" / "weapon_taxonomy_v2.yaml"
RAW_WEAPON_ROOT = REPO_ROOT / "datasets" / "raw" / "weapon"
TRAIN_OUT = REPO_ROOT / "datasets" / "training" / "weapon_v2"
EVAL_OUT = REPO_ROOT / "datasets" / "evaluation" / "weapon_v2"

# Roboflow uses "valid" but YOLO training configs expect "val"
SPLIT_MAP = {"train": "train", "valid": "val", "val": "val", "test": "test"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

random.seed(42)


# ---------------------------------------------------------------------------
# Taxonomy loading
# ---------------------------------------------------------------------------

def load_taxonomy() -> tuple[dict[str, int], dict[str, str], dict[str, int]]:
    """Return (class_id_map, alias_map, coverage_thresholds).

    class_id_map: canonical_name → new class id
    alias_map: any_alias_or_name (lowercased) → canonical_name
    coverage_thresholds: canonical_name → minimum GT box count (0 = no requirement)
    """
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        tax = yaml.safe_load(f)

    classes: dict[int, str] = tax["classes"]
    class_id_map = {name: idx for idx, name in classes.items()}

    alias_map: dict[str, str] = {}
    for canonical, aliases in tax.get("aliases", {}).items():
        alias_map[canonical.lower()] = canonical
        for alias in aliases:
            alias_map[alias.lower()] = canonical

    coverage_thresholds: dict[str, int] = tax.get("minimum_class_coverage", {})

    return class_id_map, alias_map, coverage_thresholds


# ---------------------------------------------------------------------------
# Source scanning
# ---------------------------------------------------------------------------

def find_source_dirs() -> list[Path]:
    if not RAW_WEAPON_ROOT.exists():
        return []
    return [d for d in sorted(RAW_WEAPON_ROOT.iterdir()) if d.is_dir()]


def read_data_yaml(source_dir: Path) -> dict | None:
    for candidate in (source_dir / "data.yaml", source_dir / "dataset.yaml"):
        if candidate.exists():
            with open(candidate, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return None


def build_source_class_map(
    data_yaml: dict, alias_map: dict[str, str]
) -> dict[int, str | None]:
    """Map source class index → canonical class name (None if not in taxonomy)."""
    names: list[str] = data_yaml.get("names", [])
    result: dict[int, str | None] = {}
    for idx, name in enumerate(names):
        canonical = alias_map.get(name.lower())
        result[idx] = canonical
    return result


def iter_split(source_dir: Path, split: str) -> Iterator[tuple[Path, Path]]:
    """Yield (image_path, label_path) pairs for a given split directory."""
    split_dir = source_dir / split
    if not split_dir.exists():
        return
    images_dir = split_dir / "images"
    labels_dir = split_dir / "labels"
    if not images_dir.exists():
        # Some Roboflow exports use flat layout
        images_dir = split_dir
        labels_dir = split_dir
    if not labels_dir.exists():
        return
    for img_path in sorted(images_dir.iterdir()):
        if img_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = labels_dir / (img_path.stem + ".txt")
        if label_path.exists():
            yield img_path, label_path


# ---------------------------------------------------------------------------
# Label remapping
# ---------------------------------------------------------------------------

def remap_label(
    label_path: Path,
    source_class_map: dict[int, str | None],
    class_id_map: dict[str, int],
) -> list[str] | None:
    """Return remapped label lines, or None if the image has no valid weapon annotations."""
    try:
        raw = label_path.read_text(encoding="utf-8").strip()
    except Exception:
        return None

    out_lines: list[str] = []
    for line in raw.splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            src_cls = int(parts[0])
        except ValueError:
            continue
        canonical = source_class_map.get(src_cls)
        if canonical is None:
            continue
        new_id = class_id_map[canonical]
        out_lines.append(f"{new_id} {' '.join(parts[1:5])}")

    return out_lines if out_lines else None


# ---------------------------------------------------------------------------
# Image hashing for deduplication
# ---------------------------------------------------------------------------

def image_hash(img_path: Path) -> str:
    h = hashlib.md5()
    with open(img_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _out_dirs(base: Path, split: str) -> tuple[Path, Path]:
    img_dir = base / split / "images"
    lbl_dir = base / split / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    return img_dir, lbl_dir


def unique_stem(stem: str, source_name: str) -> str:
    return f"{source_name}__{stem}"


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run(dry_run: bool, force: bool) -> dict:
    class_id_map, alias_map, coverage_thresholds = load_taxonomy()
    canonical_names = [name for name, _ in sorted(class_id_map.items(), key=lambda x: x[1])]

    if force and not dry_run:
        if TRAIN_OUT.exists():
            shutil.rmtree(TRAIN_OUT)
        if EVAL_OUT.exists():
            shutil.rmtree(EVAL_OUT)

    source_dirs = find_source_dirs()
    if not source_dirs:
        raise RuntimeError(f"No source directories found in {RAW_WEAPON_ROOT}")

    seen_hashes: set[str] = set()
    stats: dict[str, dict] = {}
    class_box_counts: dict[str, int] = defaultdict(int)

    # per-split output box counts for report
    split_class_counts: dict[str, dict[str, int]] = {
        "train": defaultdict(int),
        "val": defaultdict(int),
        "test": defaultdict(int),
    }

    for source_dir in source_dirs:
        source_name = source_dir.name
        data_yaml = read_data_yaml(source_dir)
        if data_yaml is None:
            print(f"  [{source_name}] SKIP — no data.yaml found")
            stats[source_name] = {"status": "skipped", "reason": "no data.yaml"}
            continue

        source_class_map = build_source_class_map(data_yaml, alias_map)
        mapped = {v for v in source_class_map.values() if v is not None}
        print(f"  [{source_name}] classes mapped: {sorted(mapped) or '(none)'}")

        if not mapped:
            print(f"  [{source_name}] SKIP — no taxonomy overlap")
            stats[source_name] = {"status": "skipped", "reason": "no taxonomy overlap"}
            continue

        src_stats = {
            "status": "processed",
            "mapped_classes": sorted(mapped),
            "copied": 0,
            "skipped_no_weapon": 0,
            "skipped_duplicate": 0,
        }

        for raw_split in ("train", "valid", "val", "test"):
            out_split = SPLIT_MAP.get(raw_split, raw_split)
            img_out, lbl_out = _out_dirs(TRAIN_OUT, out_split) if not dry_run else (None, None)

            for img_path, label_path in iter_split(source_dir, raw_split):
                lines = remap_label(label_path, source_class_map, class_id_map)
                if lines is None:
                    src_stats["skipped_no_weapon"] += 1
                    continue

                h = image_hash(img_path)
                if h in seen_hashes:
                    src_stats["skipped_duplicate"] += 1
                    continue
                seen_hashes.add(h)

                stem = unique_stem(img_path.stem, source_name)
                if not dry_run:
                    shutil.copy2(img_path, img_out / (stem + img_path.suffix))
                    (lbl_out / (stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")

                    # Also copy val/test images into flat eval dataset
                    if out_split in ("val", "test"):
                        eval_img, eval_lbl = _out_dirs(EVAL_OUT, "images"), _out_dirs(EVAL_OUT, "labels")[1]
                        # _out_dirs creates images/labels subdirs; for flat eval we want:
                        # datasets/evaluation/weapon_v2/images/ and labels/
                        # Fix: use direct paths
                        eval_img_dir = EVAL_OUT / "images"
                        eval_lbl_dir = EVAL_OUT / "labels"
                        eval_img_dir.mkdir(parents=True, exist_ok=True)
                        eval_lbl_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(img_path, eval_img_dir / (stem + img_path.suffix))
                        (eval_lbl_dir / (stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")

                # count per canonical class
                for line in lines:
                    cls_id = int(line.split()[0])
                    cls_name = canonical_names[cls_id]
                    class_box_counts[cls_name] += 1
                    split_class_counts[out_split][cls_name] += 1

                src_stats["copied"] += 1

        stats[source_name] = src_stats
        print(
            f"  [{source_name}] copied={src_stats['copied']}  "
            f"no_weapon={src_stats['skipped_no_weapon']}  "
            f"dup={src_stats['skipped_duplicate']}"
        )

    # Write data.yaml for training
    if not dry_run:
        nc = len(class_id_map)
        data_yaml_content = {
            "path": str(TRAIN_OUT),
            "train": "train/images",
            "val": "val/images",
            "test": "test/images",
            "nc": nc,
            "names": canonical_names,
        }
        (TRAIN_OUT / "data.yaml").write_text(
            yaml.dump(data_yaml_content, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        # Write eval data.yaml
        eval_data_yaml = {
            "path": str(EVAL_OUT),
            "val": "images",
            "nc": nc,
            "names": canonical_names,
        }
        (EVAL_OUT / "data.yaml").write_text(
            yaml.dump(eval_data_yaml, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    # Coverage check
    coverage_report: dict[str, dict] = {}
    all_coverage_met = True
    for cls_name in canonical_names:
        threshold = coverage_thresholds.get(cls_name, 0)
        count = class_box_counts.get(cls_name, 0)
        met = count >= threshold if threshold > 0 else True
        if not met:
            all_coverage_met = False
        coverage_report[cls_name] = {
            "boxes": count,
            "threshold": threshold,
            "coverage_met": met,
        }

    report = {
        "taxonomy_version": 2,
        "output_train": str(TRAIN_OUT),
        "output_eval": str(EVAL_OUT),
        "total_unique_images": len(seen_hashes),
        "split_class_box_counts": {k: dict(v) for k, v in split_class_counts.items()},
        "class_box_counts": dict(class_box_counts),
        "coverage_report": coverage_report,
        "all_coverage_met": all_coverage_met,
        "source_stats": stats,
        "dry_run": dry_run,
    }

    if not dry_run:
        report_path = TRAIN_OUT / "prep_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written → {report_path.relative_to(REPO_ROOT)}")

    return report


def print_report(report: dict) -> None:
    print("\n" + "=" * 60)
    print("WEAPON DATASET V2 — PREP REPORT")
    print("=" * 60)
    print(f"Total unique images:  {report['total_unique_images']}")
    for split, counts in report["split_class_box_counts"].items():
        total = sum(counts.values())
        print(f"  {split:<8} boxes: {total}")
    print("\nClass coverage:")
    for cls, info in report["coverage_report"].items():
        status = "OK " if info["coverage_met"] else "LOW"
        print(f"  [{status}] {cls:<12}  boxes={info['boxes']:>5}  threshold={info['threshold']}")
    if not report["all_coverage_met"]:
        print("\nWARNING: Some classes below minimum coverage threshold.")
    else:
        print("\nAll classes meet minimum coverage thresholds.")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without writing output")
    parser.add_argument("--force", action="store_true", help="Delete existing output dirs before processing")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] No files will be written.")

    print(f"Scanning weapon sources in {RAW_WEAPON_ROOT.relative_to(REPO_ROOT)} ...")
    report = run(dry_run=args.dry_run, force=args.force)
    print_report(report)

    if report["total_unique_images"] == 0:
        print("\nERROR: No images processed. Run download_roboflow_exact_datasets.py first.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
