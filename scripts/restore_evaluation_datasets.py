"""Restore Roboflow exports into the local Aegis Sentinel evaluation layout."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO_ROOT / "configs" / "evaluation" / "roboflow_sources.yaml"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
WEAPON_MODEL_CLASSES = ["pistol", "rifle", "knife", "grenade", "shotgun"]


def _load_sources() -> dict:
    with open(SOURCE_CONFIG, encoding="utf-8") as f:
        sources = yaml.safe_load(f) or {}
    if not isinstance(sources, dict):
        raise RuntimeError(f"Invalid Roboflow source config: {SOURCE_CONFIG}")
    return sources


def _repo_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _find_data_yaml(raw_dir: Path) -> Path:
    candidates = [raw_dir / "data.yaml", raw_dir / "data.yml"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    nested = sorted(
        [*raw_dir.rglob("data.yaml"), *raw_dir.rglob("data.yml")],
        key=lambda p: (len(p.relative_to(raw_dir).parts), str(p)),
    )
    if not nested:
        raise RuntimeError(f"No data.yaml found under {raw_dir}")
    return nested[0]


def _load_data_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid data.yaml: {path}")
    return data


def _parse_names(data_yaml: dict) -> list[str]:
    names = data_yaml.get("names", [])
    if isinstance(names, dict):
        return [str(names[key]) for key in sorted(names, key=lambda k: int(k))]
    if isinstance(names, list):
        return [str(name) for name in names]
    raise RuntimeError("data.yaml names must be a list or integer-keyed mapping")


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def _canonical_weapon_name(name: str) -> str:
    normalized = _normalize_name(name)
    aliases = {
        "pistol": "pistol",
        "senapan": "rifle",
        "rifle": "rifle",
        "pisau": "knife",
        "knife": "knife",
        "granat": "grenade",
        "grenade": "grenade",
        "shotgun": "shotgun",
    }
    return aliases.get(normalized, normalized)


def _resolve_split_dir(data_yaml_path: Path, data_yaml: dict, key: str) -> Path | None:
    value = data_yaml.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return None
    split_path = Path(str(value))
    if not split_path.is_absolute():
        split_path = data_yaml_path.parent / split_path
    split_path = split_path.resolve()
    if split_path.exists() and split_path.is_dir():
        return split_path
    raw_value = Path(str(value))
    if not raw_value.is_absolute():
        stripped_parts = [part for part in raw_value.parts if part not in (".", "..")]
        if stripped_parts:
            fallback = (data_yaml_path.parent / Path(*stripped_parts)).resolve()
            if fallback.exists() and fallback.is_dir():
                return fallback
    return None


def _choose_split(data_yaml_path: Path, data_yaml: dict) -> tuple[str, Path, bool]:
    for key in ("test", "valid", "val"):
        split_dir = _resolve_split_dir(data_yaml_path, data_yaml, key)
        if split_dir is not None:
            return key, split_dir, False
    train_dir = _resolve_split_dir(data_yaml_path, data_yaml, "train")
    if train_dir is None:
        raise RuntimeError("Could not find test, valid/val, or train image split from data.yaml")
    return "train_subset_20pct", train_dir, True


def _image_files(images_dir: Path) -> list[Path]:
    return sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def _deterministic_subset(images: list[Path], fraction: float = 0.2) -> list[Path]:
    if not images:
        return []
    count = max(1, math.ceil(len(images) * fraction))
    ranked = sorted(
        images,
        key=lambda p: hashlib.sha256(p.name.encode("utf-8")).hexdigest(),
    )
    return sorted(ranked[:count])


def _label_dir_for_images(images_dir: Path) -> Path:
    if images_dir.name == "images":
        return images_dir.parent / "labels"
    return images_dir.parent / "labels"


def _clean_eval_dir(eval_dir: Path) -> None:
    for name in ("images", "labels", "labels_original"):
        path = eval_dir / name
        if path.exists():
            shutil.rmtree(path)
    for name in ("dataset_summary.json", "class_mapping.json"):
        path = eval_dir / name
        if path.exists():
            path.unlink()
    (eval_dir / "images").mkdir(parents=True, exist_ok=True)
    (eval_dir / "labels").mkdir(parents=True, exist_ok=True)


def _weapon_mapping(source_names: list[str], allow_missing: bool) -> dict:
    normalized = [_canonical_weapon_name(name) for name in source_names]
    target = [_normalize_name(name) for name in WEAPON_MODEL_CLASSES]
    missing = [name for name in target if name not in normalized]
    extra = [name for name in normalized if name not in target]
    if missing and not allow_missing:
        raise RuntimeError(
            "Weapon dataset is missing required classes: "
            + ", ".join(missing)
            + ". Use --allow-missing-classes only for non-benchmark inspection."
        )
    remap = {
        src_id: target.index(name)
        for src_id, name in enumerate(normalized)
        if name in target
    }
    exact_order = normalized == target
    return {
        "task": "weapon_detection",
        "source_names": source_names,
        "model_class_names": WEAPON_MODEL_CLASSES,
        "class_id_remap": {str(k): v for k, v in remap.items()},
        "display_mapping": {name: name for name in WEAPON_MODEL_CLASSES},
        "exact_order": exact_order,
        "same_classes_different_order": not exact_order and not missing and not extra,
        "missing_classes": missing,
        "extra_classes": extra,
        "status": "PASS" if not missing else "WARN_ALLOWED_MISSING",
    }


def _phone_mapping(source_names: list[str]) -> dict:
    if len(source_names) <= 1:
        model_names = ["phone"]
    else:
        model_names = [f"phone_{idx}" for idx in range(len(source_names))]
    return {
        "task": "phone_detection",
        "source_names": source_names,
        "model_class_names": model_names,
        "class_id_remap": {str(idx): idx for idx in range(len(source_names))},
        "display_mapping": {name: "phone" for name in model_names},
        "status": "PASS",
    }


def _build_mapping(name: str, source_names: list[str], allow_missing: bool) -> dict:
    if name == "weapon":
        return _weapon_mapping(source_names, allow_missing=allow_missing)
    if name == "phone":
        return _phone_mapping(source_names)
    raise RuntimeError(f"Unsupported dataset source: {name}")


def _bbox_from_polygon(values: list[float]) -> list[float]:
    xs = values[0::2]
    ys = values[1::2]
    x_min = max(0.0, min(xs))
    y_min = max(0.0, min(ys))
    x_max = min(1.0, max(xs))
    y_max = min(1.0, max(ys))
    width = max(0.0, x_max - x_min)
    height = max(0.0, y_max - y_min)
    return [
        round(x_min + width / 2.0, 6),
        round(y_min + height / 2.0, 6),
        round(width, 6),
        round(height, 6),
    ]


def _remap_label_text(text: str, remap: dict[str, int]) -> tuple[str, Counter, int, int, int]:
    output_lines: list[str] = []
    class_counts: Counter = Counter()
    invalid_lines = 0
    converted_segmentation_lines = 0
    unsupported_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        try:
            src_id = int(parts[0])
        except ValueError:
            invalid_lines += 1
            output_lines.append(raw_line)
            continue
        dst_id = remap.get(str(src_id))
        if dst_id is None:
            unsupported_lines += 1
            continue
        if len(parts) == 5:
            normalized_values = parts[1:]
        elif len(parts) > 5 and (len(parts) - 1) % 2 == 0:
            try:
                polygon_values = [float(value) for value in parts[1:]]
            except ValueError:
                invalid_lines += 1
                output_lines.append(raw_line)
                continue
            normalized_values = [str(value) for value in _bbox_from_polygon(polygon_values)]
            converted_segmentation_lines += 1
        else:
            invalid_lines += 1
            output_lines.append(raw_line)
            continue
        parts[0] = str(dst_id)
        parts[1:] = normalized_values
        class_counts[str(dst_id)] += 1
        output_lines.append(" ".join(parts))
    suffix = "\n" if output_lines else ""
    return "\n".join(output_lines) + suffix, class_counts, invalid_lines, converted_segmentation_lines, unsupported_lines


def _restore_one(name: str, source: dict, allow_missing_classes: bool) -> dict:
    raw_dir = _repo_path(source["raw_dir"])
    eval_dir = _repo_path(source["eval_dir"])
    if not raw_dir.exists():
        raise RuntimeError(f"Raw dataset directory not found for {name}: {raw_dir}")

    data_yaml_path = _find_data_yaml(raw_dir)
    data_yaml = _load_data_yaml(data_yaml_path)
    source_names = _parse_names(data_yaml)
    mapping = _build_mapping(name, source_names, allow_missing=allow_missing_classes)

    split_name, images_dir, is_subset = _choose_split(data_yaml_path, data_yaml)
    labels_dir = _label_dir_for_images(images_dir)
    images = _image_files(images_dir)
    if is_subset:
        images = _deterministic_subset(images)
    if not images:
        raise RuntimeError(f"No images found for {name} split '{split_name}' at {images_dir}")

    _clean_eval_dir(eval_dir)
    out_images_dir = eval_dir / "images"
    out_labels_dir = eval_dir / "labels"
    labels_original_dir = eval_dir / "labels_original"

    remap = mapping["class_id_remap"]
    remap_needed = any(str(src_id) != str(dst_id) for src_id, dst_id in remap.items())
    if remap_needed:
        labels_original_dir.mkdir(parents=True, exist_ok=True)

    class_distribution: Counter = Counter()
    missing_source_labels = 0
    invalid_label_lines = 0
    converted_segmentation_lines = 0
    unsupported_label_lines = 0
    positive_images = 0

    for image_path in images:
        out_image = out_images_dir / image_path.name
        shutil.copy2(image_path, out_image)

        source_label = labels_dir / f"{image_path.stem}.txt"
        out_label = out_labels_dir / f"{image_path.stem}.txt"
        if source_label.exists():
            raw_text = source_label.read_text(encoding="utf-8")
        else:
            raw_text = ""
            missing_source_labels += 1

        remapped_text, counts, invalid_count, converted_count, unsupported_count = _remap_label_text(raw_text, remap)
        if (remap_needed or converted_count > 0 or unsupported_count > 0) and source_label.exists():
            labels_original_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_label, labels_original_dir / source_label.name)
        out_label.write_text(remapped_text, encoding="utf-8")
        invalid_label_lines += invalid_count
        converted_segmentation_lines += converted_count
        unsupported_label_lines += unsupported_count
        class_distribution.update(counts)
        if sum(counts.values()) > 0:
            positive_images += 1

    summary = {
        "task": source.get("expected_task"),
        "source": {
            "workspace": source.get("workspace"),
            "project": source.get("project"),
            "version": source.get("version"),
            "format": source.get("format"),
            "raw_dir": str(raw_dir.relative_to(REPO_ROOT)),
            "data_yaml": str(data_yaml_path.relative_to(REPO_ROOT)),
            "split_used": split_name,
            "split_images_dir": str(images_dir.relative_to(REPO_ROOT)),
            "train_subset_20pct": is_subset,
        },
        "evaluation_dir": str(eval_dir.relative_to(REPO_ROOT)),
        "images_count": len(images),
        "labels_count": len(list(out_labels_dir.glob("*.txt"))),
        "positive_images_count": positive_images,
        "negative_images_count": len(images) - positive_images,
        "total_boxes": sum(class_distribution.values()),
        "class_distribution": dict(sorted(class_distribution.items(), key=lambda item: int(item[0]))),
        "missing_source_labels": missing_source_labels,
        "invalid_label_lines": invalid_label_lines,
        "converted_segmentation_lines": converted_segmentation_lines,
        "unsupported_label_lines": unsupported_label_lines,
        "remapping_performed": remap_needed,
        "status": "PASS" if invalid_label_lines == 0 else "WARN_INVALID_LABELS",
    }

    with open(eval_dir / "class_mapping.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    with open(eval_dir / "dataset_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"Restored {name}: {summary['images_count']} images, "
        f"{summary['labels_count']} labels, {summary['total_boxes']} boxes, "
        f"split={split_name}, remap={remap_needed}"
    )
    return summary


def _selected_sources(sources: dict, only: str | None, all_sources: bool) -> list[str]:
    if only and all_sources:
        raise RuntimeError("Use either --only or --all, not both")
    if only:
        if only not in sources:
            raise RuntimeError(f"Unknown source '{only}'. Available: {', '.join(sorted(sources))}")
        return [only]
    return list(sources.keys())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("phone", "weapon"), help="Restore only one dataset")
    parser.add_argument("--all", action="store_true", help="Restore all configured datasets")
    parser.add_argument(
        "--allow-missing-classes",
        action="store_true",
        help="Allow weapon datasets with missing required classes for inspection only",
    )
    args = parser.parse_args()

    sources = _load_sources()
    for name in _selected_sources(sources, args.only, args.all):
        _restore_one(name, sources[name], allow_missing_classes=args.allow_missing_classes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
