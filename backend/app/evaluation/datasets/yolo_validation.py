"""Strict YOLO dataset validation for real detection benchmarks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


class YoloDatasetValidationError(ValueError):
    """Raised when a YOLO evaluation dataset is not benchmark-ready."""


@dataclass(frozen=True)
class YoloDatasetValidationSummary:
    images_count: int
    labels_count: int
    positive_images_count: int
    negative_images_count: int
    annotations_count: int

    def to_dict(self) -> dict:
        return {
            "images_count": self.images_count,
            "labels_count": self.labels_count,
            "positive_images_count": self.positive_images_count,
            "negative_images_count": self.negative_images_count,
            "annotations_count": self.annotations_count,
        }


def validate_yolo_detection_dataset(
    *,
    images_dir: str | Path,
    labels_dir: str | Path,
    class_names: list[str] | None = None,
) -> YoloDatasetValidationSummary:
    """
    Validate a YOLO detection evaluation dataset.

    Required invariants:
    - images and labels directories exist
    - every image has a same-stem .txt label file
    - every non-empty label line has exactly 5 fields
    - class_id is an integer in the configured class range
    - bbox values are numeric and normalized to [0, 1]
    - empty label files are allowed for negative images
    """
    images_path = Path(images_dir)
    labels_path = Path(labels_dir)
    errors: list[str] = []

    if not images_path.exists() or not images_path.is_dir():
        errors.append(f"images directory not found: {images_path}")
    if not labels_path.exists() or not labels_path.is_dir():
        errors.append(f"labels directory not found: {labels_path}")
    if errors:
        raise YoloDatasetValidationError(_format_errors(errors))

    image_files = sorted(
        p for p in images_path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    label_files = sorted(p for p in labels_path.glob("*.txt") if p.is_file())

    if not image_files:
        errors.append(f"no image files found in: {images_path}")

    image_stems = {p.stem for p in image_files}
    label_stems = {p.stem for p in label_files}

    for image_file in image_files:
        expected_label = labels_path / f"{image_file.stem}.txt"
        if image_file.stem not in label_stems:
            errors.append(f"missing label file for image: {image_file} -> {expected_label}")

    for label_file in label_files:
        if label_file.stem not in image_stems:
            errors.append(f"orphan label file without matching image: {label_file}")

    max_class_id = len(class_names or []) - 1
    annotations_count = 0
    positive_stems: set[str] = set()

    for label_file in label_files:
        try:
            raw_text = label_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{label_file}: cannot decode as UTF-8 ({exc})")
            continue

        has_annotation = False
        for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 5:
                errors.append(
                    f"{label_file}:{line_number}: expected 5 fields, found {len(parts)}"
                )
                continue

            try:
                class_id = int(parts[0])
            except ValueError:
                errors.append(f"{label_file}:{line_number}: class_id is not an integer: {parts[0]}")
                continue

            if class_id < 0 or (max_class_id >= 0 and class_id > max_class_id):
                valid_range = f"0..{max_class_id}" if max_class_id >= 0 else ">= 0"
                errors.append(
                    f"{label_file}:{line_number}: invalid class_id {class_id}; valid range is {valid_range}"
                )

            try:
                bbox_values = [float(value) for value in parts[1:]]
            except ValueError:
                errors.append(f"{label_file}:{line_number}: bbox values must be numeric")
                continue

            for value_index, value in enumerate(bbox_values, start=1):
                if not math.isfinite(value) or value < 0.0 or value > 1.0:
                    errors.append(
                        f"{label_file}:{line_number}: bbox field {value_index}={value} is outside [0, 1]"
                    )

            annotations_count += 1
            has_annotation = True

        if has_annotation:
            positive_stems.add(label_file.stem)

    if errors:
        raise YoloDatasetValidationError(_format_errors(errors))

    positive_images_count = len(positive_stems & image_stems)
    negative_images_count = len(image_files) - positive_images_count

    return YoloDatasetValidationSummary(
        images_count=len(image_files),
        labels_count=len(label_files),
        positive_images_count=positive_images_count,
        negative_images_count=negative_images_count,
        annotations_count=annotations_count,
    )


def _format_errors(errors: list[str]) -> str:
    max_errors = 25
    visible = errors[:max_errors]
    suffix = ""
    if len(errors) > max_errors:
        suffix = f"\n... and {len(errors) - max_errors} more validation errors"
    return "YOLO dataset validation failed:\n" + "\n".join(f"- {error}" for error in visible) + suffix
