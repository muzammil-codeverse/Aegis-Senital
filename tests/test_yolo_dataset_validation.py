from __future__ import annotations

from pathlib import Path

import pytest


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00d\x00\x00\x00d"
    b"\x08\x02\x00\x00\x00"
)


def _write_png(path: Path) -> None:
    path.write_bytes(_TINY_PNG)


def test_yolo_dataset_validation_allows_empty_negative_labels(tmp_path: Path):
    from backend.app.evaluation.datasets.yolo_validation import validate_yolo_detection_dataset

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    _write_png(images / "positive.png")
    _write_png(images / "negative.png")
    (labels / "positive.txt").write_text("0 0.5 0.5 0.25 0.25\n", encoding="utf-8")
    (labels / "negative.txt").write_text("", encoding="utf-8")

    summary = validate_yolo_detection_dataset(
        images_dir=images,
        labels_dir=labels,
        class_names=["phone"],
    )

    assert summary.images_count == 2
    assert summary.labels_count == 2
    assert summary.positive_images_count == 1
    assert summary.negative_images_count == 1
    assert summary.annotations_count == 1


def test_yolo_dataset_validation_reports_label_errors(tmp_path: Path):
    from backend.app.evaluation.datasets.yolo_validation import (
        YoloDatasetValidationError,
        validate_yolo_detection_dataset,
    )

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    _write_png(images / "bad.png")
    (labels / "bad.txt").write_text("3 1.2 0.5 0.2\n", encoding="utf-8")

    with pytest.raises(YoloDatasetValidationError) as exc_info:
        validate_yolo_detection_dataset(
            images_dir=images,
            labels_dir=labels,
            class_names=["phone"],
        )

    message = str(exc_info.value)
    assert "expected 5 fields" in message
    assert "bad.txt:1" in message


def test_yolo_loader_converts_normalized_boxes_to_absolute_xyxy(tmp_path: Path):
    from backend.app.evaluation.datasets.coco_yolo_loader import CocoYoloLoader

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    _write_png(images / "sample.png")
    (labels / "sample.txt").write_text("0 0.5 0.5 0.2 0.4\n", encoding="utf-8")

    samples = CocoYoloLoader(
        str(tmp_path),
        class_names=["phone"],
        images_dir=str(images),
        labels_dir=str(labels),
    ).load_yolo_annotations()

    assert samples[0]["width"] == 100
    assert samples[0]["height"] == 100
    assert samples[0]["annotations"][0]["bbox_xyxy"] == [40.0, 30.0, 60.0, 70.0]
