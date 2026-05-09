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
        version: str | None = None,
        required: bool = False,
        loader: str = "generic",
        metadata: dict | None = None,
    ) -> None:
        self.name = name
        self.task = task
        self.path = path
        self.version = version
        self.required = required
        self.loader = loader
        self.metadata = metadata or {}

    def exists(self) -> bool:
        return Path(self.path).exists()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "task": self.task,
            "path": self.path,
            "version": self.version,
            "required": self.required,
            "loader": self.loader,
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
            entry = DatasetEntry(
                name=name,
                task=ds_cfg.get("task", "unknown"),
                path=ds_cfg.get("path", ""),
                version=ds_cfg.get("version"),
                required=bool(ds_cfg.get("required", False)),
                loader=ds_cfg.get("loader", "generic"),
                metadata=ds_cfg.get("metadata", {}),
            )
            self._datasets[name] = entry
            if not entry.exists():
                msg = f"Dataset '{name}' path not found: {entry.path}"
                if entry.required:
                    raise FileNotFoundError(msg)
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
            raise FileNotFoundError(
                f"Required dataset '{name}' path not found: {entry.path}"
            )
        return entry

    def list_all(self) -> list[dict]:
        return [e.to_dict() for e in self._datasets.values()]

    def available(self, task: str | None = None) -> list[DatasetEntry]:
        entries = [e for e in self._datasets.values() if e.exists()]
        if task:
            entries = [e for e in entries if e.task == task]
        return entries
