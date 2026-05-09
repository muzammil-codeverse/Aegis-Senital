"""Phase 25 — Face recognition evaluation dataset loader."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FaceEvalLoader:
    """
    Loads a face evaluation dataset.

    Expected structure:
        dataset_path/
            pairs.txt    (LFW-style: name1 idx1 name2 idx2 [same=1/diff=0])
            images/
                identity_name/
                    image_001.jpg ...
    """

    def __init__(self, dataset_path: str) -> None:
        self._path = Path(dataset_path)

    def load_pairs(self) -> list[dict]:
        pairs_file = self._path / "pairs.txt"
        if not pairs_file.exists():
            logger.warning("Face pairs file not found: %s", pairs_file)
            return []

        pairs = []
        try:
            lines = pairs_file.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 3:
                    name, idx1, idx2 = parts[0], int(parts[1]), int(parts[2])
                    img1 = self._resolve_image(name, idx1)
                    img2 = self._resolve_image(name, idx2)
                    pairs.append({"image1": img1, "image2": img2, "same": True, "identity": name})
                elif len(parts) == 4:
                    name1, idx1, name2, idx2 = parts[0], int(parts[1]), parts[2], int(parts[3])
                    img1 = self._resolve_image(name1, idx1)
                    img2 = self._resolve_image(name2, idx2)
                    pairs.append({"image1": img1, "image2": img2, "same": False, "identity": None})
        except Exception as exc:
            logger.error("Failed to parse face pairs file: %s", exc)

        logger.info("FaceEvalLoader: loaded %d pairs from %s", len(pairs), self._path)
        return pairs

    def _resolve_image(self, identity: str, idx: int) -> str | None:
        img_dir = self._path / "images" / identity
        if not img_dir.exists():
            return None
        candidates = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
        if idx - 1 < len(candidates):
            return str(candidates[idx - 1])
        return None

    def load_gallery(self) -> list[dict]:
        """Load all images as gallery: {identity, image_path}."""
        images_dir = self._path / "images"
        if not images_dir.exists():
            return []
        gallery = []
        for identity_dir in sorted(images_dir.iterdir()):
            if not identity_dir.is_dir():
                continue
            for img_path in sorted(identity_dir.glob("*.jpg")) + sorted(identity_dir.glob("*.png")):
                gallery.append({"identity": identity_dir.name, "image_path": str(img_path)})
        return gallery
