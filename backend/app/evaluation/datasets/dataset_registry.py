"""Phase 25 — Dataset registry: maps dataset names to loaders and paths."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DatasetEntry:
    def __init__(
        self,
        name: str,
        task: str,
        path: str,
        dataset_type: str = "generic",
        version: str | None = None,
        required: bool = False,
        loader: str = "generic",
        images_dir: str | None = None,
        labels_dir: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.name = name
        self.task = task
        self.path = path
        self.dataset_type = dataset_type
        self.version = version
        self.required = required
        self.loader = loader
        self.images_dir = images_dir
        self.labels_dir = labels_dir
        self.metadata = metadata or {}

    def exists(self) -> bool:
        if self.dataset_type == "coco_yolo":
            return bool(self.images_dir and Path(self.images_dir).exists()) and bool(
                self.labels_dir and Path(self.labels_dir).exists()
            )
        return Path(self.path).exists()

    def missing_paths(self) -> list[str]:
        missing: list[str] = []
        if self.dataset_type == "coco_yolo":
            if self.images_dir and not Path(self.images_dir).exists():
                missing.append(self.images_dir)
            if self.labels_dir and not Path(self.labels_dir).exists():
                missing.append(self.labels_dir)
            return missing
        if self.path and not Path(self.path).exists():
            missing.append(self.path)
        return missing

    def missing_message(self) -> str:
        missing = self.missing_paths()
        if not missing:
            return ""
        if self.dataset_type == "coco_yolo":
            return f"Dataset '{self.name}' missing required paths: {', '.join(missing)}"
        return f"Dataset '{self.name}' path not found: {missing[0]}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "task": self.task,
            "path": self.path,
            "type": self.dataset_type,
            "version": self.version,
            "required": self.required,
            "loader": self.loader,
            "images_dir": self.images_dir,
            "labels_dir": self.labels_dir,
            "exists": self.exists(),
        }


class DatasetRegistry:
    def __init__(self, config: dict | None = None) -> None:
        self._datasets: dict[str, DatasetEntry] = {}
        if config:
            self._load_from_config(config)

    def _load_from_config(self, config: dict) -> None:
        datasets_cfg = config.get("datasets", {})
        for name, ds_cfg in datasets_cfg.items():
            if not isinstance(ds_cfg, dict):
                continue
            dataset_type = str(ds_cfg.get("type", ds_cfg.get("loader", "generic")))
            images_dir = ds_cfg.get("images_dir")
            labels_dir = ds_cfg.get("labels_dir")
            path = ds_cfg.get("path", "")
            if dataset_type == "coco_yolo" and not path:
                if images_dir:
                    try:
                        path = str(Path(images_dir).parent.parent)
                    except Exception:
                        path = ""
            entry = DatasetEntry(
                name=name,
                task=ds_cfg.get("task", "unknown"),
                path=path,
                dataset_type=dataset_type,
                version=ds_cfg.get("version"),
                required=bool(ds_cfg.get("required", False)),
                loader=ds_cfg.get("loader", dataset_type),
                images_dir=images_dir,
                labels_dir=labels_dir,
                metadata={
                    **ds_cfg.get("metadata", {}),
                    "class_names": list(ds_cfg.get("class_names", [])),
                },
            )
            self._datasets[name] = entry
            if not entry.exists():
                msg = entry.missing_message() or f"Dataset '{name}' path not found: {entry.path}"
                if entry.required:
                    logger.warning("%s (required — will fail on use)", msg)
                else:
                    logger.warning("%s (optional — skipping)", msg)

    def register(self, entry: DatasetEntry) -> None:
        self._datasets[entry.name] = entry

    def get(self, name: str) -> DatasetEntry | None:
        return self._datasets.get(name)

    def get_required(self, name: str) -> DatasetEntry:
        entry = self.get(name)
        if entry is None:
            raise FileNotFoundError(f"Required dataset '{name}' not registered")
        if not entry.exists():
            raise FileNotFoundError(entry.missing_message() or f"Required dataset '{name}' path not found: {entry.path}")
        return entry

    def list_all(self) -> list[dict]:
        return [e.to_dict() for e in self._datasets.values()]

    def available(self, task: str | None = None) -> list[DatasetEntry]:
        entries = [e for e in self._datasets.values() if e.exists()]
        if task:
            entries = [e for e in entries if e.task == task]
        return entries
