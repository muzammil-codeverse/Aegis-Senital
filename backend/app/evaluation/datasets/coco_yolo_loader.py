"""Phase 25 — COCO/YOLO-format dataset loader for detection evaluation."""
from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

from backend.app.evaluation.datasets.yolo_validation import IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)


class CocoYoloLoader:
    """
    Loads YOLO-format annotation directories or COCO JSON annotation files.

    YOLO format expected:
        dataset_path/
            images/
            labels/   # one .txt per image: class cx cy w h (normalized)

    COCO JSON format expected:
        annotations.json  (standard COCO format)
        images/
    """

    def __init__(
        self,
        dataset_path: str,
        class_names: list[str] | None = None,
        *,
        images_dir: str | None = None,
        labels_dir: str | None = None,
    ) -> None:
        self._path = Path(dataset_path)
        self._class_names = class_names or []
        self._images_dir = Path(images_dir) if images_dir else self._path / "images"
        self._labels_dir = Path(labels_dir) if labels_dir else self._path / "labels"

    def load_yolo_annotations(self) -> list[dict]:
        """
        Return list of sample dicts:
            { image_path, width, height, annotations: [{class_id, class_name, bbox_xywh_norm}] }
        Returns empty list if dataset path does not exist.
        """
        labels_dir = self._labels_dir
        images_dir = self._images_dir
        if not labels_dir.exists():
            logger.warning("YOLO labels dir not found: %s", labels_dir)
            return []
        if not images_dir.exists():
            logger.warning("YOLO images dir not found: %s", images_dir)
            return []

        samples = []
        image_files = sorted(
            p for p in images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
        for image_file in image_files:
            image_stem = image_file.stem
            label_file = labels_dir / f"{image_stem}.txt"
            image_width, image_height = _read_image_size(image_file)

            annotations = []
            try:
                lines = label_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    if len(parts) != 5:
                        continue
                    class_id = int(parts[0])
                    cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    bbox_xyxy = _yolo_norm_to_xyxy(cx, cy, w, h, image_width, image_height)
                    class_name = (
                        self._class_names[class_id]
                        if class_id < len(self._class_names)
                        else str(class_id)
                    )
                    annotations.append({
                        "class_id": class_id,
                        "class_name": class_name,
                        "bbox_cxcywh_norm": [cx, cy, w, h],
                        "bbox_xyxy": bbox_xyxy,
                    })
            except Exception as exc:
                logger.warning("Failed to parse label file %s: %s", label_file, exc)

            samples.append({
                "image_path": str(image_file),
                "sample_id": image_stem,
                "width": image_width,
                "height": image_height,
                "annotations": annotations,
            })

        logger.info("CocoYoloLoader: loaded %d samples from %s", len(samples), self._path)
        return samples

    def load_coco_json(self, annotation_file: str) -> list[dict]:
        """Load COCO JSON annotations and return per-image sample list."""
        import json
        ann_path = Path(annotation_file)
        if not ann_path.exists():
            logger.warning("COCO annotation file not found: %s", ann_path)
            return []

        with open(ann_path, encoding="utf-8") as f:
            data = json.load(f)

        categories = {c["id"]: c["name"] for c in data.get("categories", [])}
        images = {img["id"]: img for img in data.get("images", [])}
        ann_by_image: dict[int, list] = {}
        for ann in data.get("annotations", []):
            img_id = ann["image_id"]
            ann_by_image.setdefault(img_id, []).append(ann)

        samples = []
        for img_id, img_meta in images.items():
            anns = ann_by_image.get(img_id, [])
            annotations = []
            for ann in anns:
                x, y, w, h = ann["bbox"]
                cat_name = categories.get(ann["category_id"], str(ann["category_id"]))
                annotations.append({
                    "class_id": ann["category_id"],
                    "class_name": cat_name,
                    "bbox_xyxy": [x, y, x + w, y + h],
                    "area": ann.get("area", w * h),
                })
            image_path = str(self._path / "images" / img_meta["file_name"])
            samples.append({
                "image_path": image_path,
                "sample_id": img_meta["file_name"],
                "width": img_meta.get("width"),
                "height": img_meta.get("height"),
                "annotations": annotations,
            })

        logger.info("CocoYoloLoader: loaded %d COCO samples from %s", len(samples), annotation_file)
        return samples


def _yolo_norm_to_xyxy(
    cx: float,
    cy: float,
    width: float,
    height: float,
    image_width: int,
    image_height: int,
) -> list[float]:
    x1 = (cx - width / 2.0) * image_width
    y1 = (cy - height / 2.0) * image_height
    x2 = (cx + width / 2.0) * image_width
    y2 = (cy + height / 2.0) * image_height
    return [
        max(0.0, min(float(image_width), x1)),
        max(0.0, min(float(image_height), y1)),
        max(0.0, min(float(image_width), x2)),
        max(0.0, min(float(image_height), y2)),
    ]


def _read_image_size(image_path: Path) -> tuple[int, int]:
    suffix = image_path.suffix.lower()
    with open(image_path, "rb") as f:
        if suffix == ".png":
            header = f.read(24)
            if len(header) >= 24 and header.startswith(b"\x89PNG\r\n\x1a\n"):
                return struct.unpack(">II", header[16:24])
        if suffix == ".bmp":
            header = f.read(26)
            if len(header) >= 26 and header.startswith(b"BM"):
                width = int.from_bytes(header[18:22], "little", signed=True)
                height = abs(int.from_bytes(header[22:26], "little", signed=True))
                if width > 0 and height > 0:
                    return width, height
        if suffix in (".jpg", ".jpeg"):
            return _read_jpeg_size(f)
    raise ValueError(f"unsupported or unreadable image dimensions: {image_path}")


def _read_jpeg_size(f) -> tuple[int, int]:
    f.seek(0)
    if f.read(2) != b"\xff\xd8":
        raise ValueError("invalid JPEG header")

    while True:
        marker_prefix = f.read(1)
        if not marker_prefix:
            break
        if marker_prefix != b"\xff":
            continue
        marker = f.read(1)
        while marker == b"\xff":
            marker = f.read(1)
        if not marker:
            break
        marker_int = marker[0]
        if marker_int in (0xD8, 0xD9):
            continue
        length_bytes = f.read(2)
        if len(length_bytes) != 2:
            break
        segment_length = int.from_bytes(length_bytes, "big")
        if segment_length < 2:
            break
        if marker_int in (
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        ):
            data = f.read(5)
            if len(data) != 5:
                break
            height = int.from_bytes(data[1:3], "big")
            width = int.from_bytes(data[3:5], "big")
            return width, height
        f.seek(segment_length - 2, 1)

    raise ValueError("JPEG size marker not found")
