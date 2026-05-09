"""Phase 25 — MOTChallenge-format dataset loader for tracking evaluation."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MOTLoader:
    """
    Loads MOTChallenge-style tracking annotations.

    Expected structure:
        sequence_dir/
            gt/gt.txt      (ground truth: frame, id, x, y, w, h, conf, class, visibility)
            det/det.txt    (detections)
            img1/          (frames)
    """

    def __init__(self, sequence_path: str) -> None:
        self._path = Path(sequence_path)

    def load_ground_truth(self) -> list[dict]:
        gt_file = self._path / "gt" / "gt.txt"
        if not gt_file.exists():
            logger.warning("MOT gt.txt not found: %s", gt_file)
            return []

        records = []
        try:
            lines = gt_file.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) < 6:
                    continue
                frame_id = int(parts[0])
                track_id = int(parts[1])
                x, y, w, h = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
                conf = float(parts[6]) if len(parts) > 6 else 1.0
                class_id = int(parts[7]) if len(parts) > 7 else 1
                visibility = float(parts[8]) if len(parts) > 8 else 1.0
                records.append({
                    "frame_id": frame_id,
                    "track_id": track_id,
                    "bbox_xywh": [x, y, w, h],
                    "conf": conf,
                    "class_id": class_id,
                    "visibility": visibility,
                })
        except Exception as exc:
            logger.error("Failed to parse MOT gt.txt: %s", exc)

        logger.info("MOTLoader: loaded %d gt records from %s", len(records), self._path)
        return records

    def load_detections(self) -> list[dict]:
        det_file = self._path / "det" / "det.txt"
        if not det_file.exists():
            logger.warning("MOT det.txt not found: %s", det_file)
            return []

        records = []
        try:
            lines = det_file.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) < 6:
                    continue
                frame_id = int(parts[0])
                x, y, w, h = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
                conf = float(parts[6]) if len(parts) > 6 else 1.0
                records.append({
                    "frame_id": frame_id,
                    "bbox_xywh": [x, y, w, h],
                    "conf": conf,
                })
        except Exception as exc:
            logger.error("Failed to parse MOT det.txt: %s", exc)

        return records

    def get_frame_paths(self) -> list[Path]:
        img_dir = self._path / "img1"
        if not img_dir.exists():
            return []
        return sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))

    def group_by_frame(self, records: list[dict]) -> dict[int, list[dict]]:
        by_frame: dict[int, list] = {}
        for r in records:
            fid = r["frame_id"]
            by_frame.setdefault(fid, []).append(r)
        return by_frame
