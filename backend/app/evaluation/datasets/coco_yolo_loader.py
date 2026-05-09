"""Phase 25 — COCO/YOLO-format dataset loader for detection evaluation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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

        samples = []
        for label_file in sorted(labels_dir.glob("*.txt")):
            image_stem = label_file.stem
            image_path = None
            for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                candidate = images_dir / (image_stem + ext)
                if candidate.exists():
                    image_path = str(candidate)
                    break

            annotations = []
            try:
                lines = label_file.read_text(encoding="utf-8").strip().splitlines()
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    class_id = int(parts[0])
                    cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    class_name = (
                        self._class_names[class_id]
                        if class_id < len(self._class_names)
                        else str(class_id)
                    )
                    annotations.append({
                        "class_id": class_id,
                        "class_name": class_name,
                        "bbox_cxcywh_norm": [cx, cy, w, h],
                    })
            except Exception as exc:
                logger.warning("Failed to parse label file %s: %s", label_file, exc)

            samples.append({
                "image_path": image_path,
                "sample_id": image_stem,
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
