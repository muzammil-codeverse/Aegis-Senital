import os
from pathlib import Path


def count_images(root_dir: str) -> int:
    """
    Recursively count image files in dataset directory.
    Safe for missing directories.
    """
    if not root_dir or not os.path.exists(root_dir):
        return 0

    img_exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    total = 0

    for root, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(img_exts):
                total += 1

    return total


def validate_splits(dataset_root: str, splits=("train", "valid", "test")):
    """
    Auto-detect Roboflow or YOLO layout:
    - Roboflow: train/labels, valid/labels
    - YOLO: images/labels split structure
    """
    if not os.path.exists(dataset_root):
        raise SystemExit(f"Dataset root not found: {dataset_root}")

    for split in splits:
        labels_path = os.path.join(dataset_root, split, "labels")
        images_path = os.path.join(dataset_root, split, "images")

        if not os.path.exists(labels_path):
            raise SystemExit(f"Missing labels: {labels_path}")

        if not os.path.exists(images_path):
            raise SystemExit(f"Missing images: {images_path}")


def check_labels(label_dir: str):
    """
    Lightweight sanity check (YOLO format enforcement placeholder).
    """
    if not os.path.exists(label_dir):
        raise SystemExit(f"Label directory not found: {label_dir}")
