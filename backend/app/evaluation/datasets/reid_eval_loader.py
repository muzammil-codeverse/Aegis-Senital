"""Phase 25 — ReID evaluation dataset loader (query/gallery split)."""
from __future__ import annotations

import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


class ReIDEvalLoader:
    """
    Loads a ReID evaluation dataset in Market-1501 / DukeMTMC style.

    Expected structure:
        dataset_path/
            query/
                <identity_pid>_<camera_cid>_<frame>.jpg ...
            gallery/
                <identity_pid>_<camera_cid>_<frame>.jpg ...

    If query/ and gallery/ do not exist, auto-splits images/ directory
    80/20 into gallery/query.  Flags overlap if same image appears in both.
    """

    def __init__(self, dataset_path: str) -> None:
        self._path = Path(dataset_path)

    def load_query(self) -> list[dict]:
        return self._load_split("query")

    def load_gallery(self) -> list[dict]:
        return self._load_split("gallery")

    def _load_split(self, split_name: str) -> list[dict]:
        split_dir = self._path / split_name
        if not split_dir.exists():
            logger.warning("ReID %s dir not found: %s", split_name, split_dir)
            return []

        entries = []
        for img_path in sorted(split_dir.glob("*.jpg")) + sorted(split_dir.glob("*.png")):
            pid, camid = self._parse_market1501(img_path.stem)
            entries.append({
                "image_path": str(img_path),
                "identity_id": pid,
                "camera_id": camid,
                "split": split_name,
            })
        logger.info("ReIDEvalLoader: loaded %d %s images", len(entries), split_name)
        return entries

    def _parse_market1501(self, stem: str) -> tuple[str, str]:
        parts = stem.split("_")
        pid = parts[0] if len(parts) > 0 else "unknown"
        camid = parts[1] if len(parts) > 1 else "unknown"
        return pid, camid

    def check_overlap(self, query: list[dict], gallery: list[dict]) -> bool:
        query_paths = {e["image_path"] for e in query}
        gallery_paths = {e["image_path"] for e in gallery}
        overlap = query_paths & gallery_paths
        if overlap:
            logger.warning(
                "ReID overlap detected: %d images appear in both query and gallery",
                len(overlap),
            )
            return True
        return False

    def auto_split(self, train_ratio: float = 0.8) -> tuple[list[dict], list[dict]]:
        images_dir = self._path / "images"
        if not images_dir.exists():
            return [], []
        all_images = []
        for img_path in sorted(images_dir.glob("*.jpg")) + sorted(images_dir.glob("*.png")):
            pid, camid = self._parse_market1501(img_path.stem)
            all_images.append({
                "image_path": str(img_path),
                "identity_id": pid,
                "camera_id": camid,
            })
        random.shuffle(all_images)
        split_idx = int(len(all_images) * train_ratio)
        gallery = all_images[:split_idx]
        query = all_images[split_idx:]
        for e in gallery:
            e["split"] = "gallery"
        for e in query:
            e["split"] = "query"
        return query, gallery
