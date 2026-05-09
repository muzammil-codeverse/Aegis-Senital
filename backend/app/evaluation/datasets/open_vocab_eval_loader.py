"""Phase 25 — Open-vocab evaluation dataset loader."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OpenVocabEvalLoader:
    """
    Loads labeled data for open-vocab prompt evaluation.

    Expected format (JSONL):
        { "image_path": "...", "prompt_id": "weapon_visible",
          "label": "weapon", "has_detection": true,
          "bbox": [x1, y1, x2, y2] | null }

    Each entry corresponds to one image/prompt pair with ground truth.
    """

    def __init__(self, dataset_path: str) -> None:
        self._path = Path(dataset_path)

    def load(self) -> list[dict]:
        ann_file = self._path / "annotations.jsonl"
        if not ann_file.exists():
            ann_file = self._path / "annotations.json"
            if ann_file.exists():
                return self._load_json(ann_file)
            logger.warning("Open-vocab annotations not found: %s", self._path)
            return []
        return self._load_jsonl(ann_file)

    def _load_jsonl(self, path: Path) -> list[dict]:
        samples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed JSONL line: %s", exc)
        logger.info("OpenVocabEvalLoader: loaded %d samples (JSONL)", len(samples))
        return samples

    def _load_json(self, path: Path) -> list[dict]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            logger.info("OpenVocabEvalLoader: loaded %d samples (JSON)", len(data))
            return data
        logger.warning("Unexpected JSON format in %s — expected list", path)
        return []

    def group_by_prompt(self, samples: list[dict]) -> dict[str, list[dict]]:
        by_prompt: dict[str, list] = {}
        for s in samples:
            pid = s.get("prompt_id", "unknown")
            by_prompt.setdefault(pid, []).append(s)
        return by_prompt
