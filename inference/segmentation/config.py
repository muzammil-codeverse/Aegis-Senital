from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Sam2Config:
    checkpoint_path: str = "models/segmentation/sam2/checkpoint.pt"
    model_config: str = "configs/segmentation/sam2.yaml"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Sam2Config":
        data = data or {}
        return cls(
            checkpoint_path=str(data.get("checkpoint_path", cls.checkpoint_path)),
            model_config=str(data.get("model_config", cls.model_config)),
        )

    @property
    def checkpoint(self) -> Path:
        return _resolve_path(self.checkpoint_path)

    @property
    def config_path(self) -> Path:
        return _resolve_path(self.model_config)


@dataclass
class SegmentationConfig:
    enabled: bool = True
    provider: str = "sam2"
    device: str = "cuda"
    auto_load: bool = False
    fail_open: bool = True
    max_masks_per_frame: int = 20
    min_box_area_px: int = 64
    mask_encoding: str = "rle"
    fallback_box_mask: bool = False
    sam2: Sam2Config = field(default_factory=Sam2Config)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SegmentationConfig":
        data = data or {}
        if "segmentation" in data and isinstance(data["segmentation"], dict):
            data = data["segmentation"]
        cfg = cls(
            enabled=bool(data.get("enabled", cls.enabled)),
            provider=str(data.get("provider", cls.provider)).lower(),
            device=str(data.get("device", cls.device)).lower(),
            auto_load=bool(data.get("auto_load", cls.auto_load)),
            fail_open=bool(data.get("fail_open", cls.fail_open)),
            max_masks_per_frame=max(0, int(data.get("max_masks_per_frame", cls.max_masks_per_frame))),
            min_box_area_px=max(0, int(data.get("min_box_area_px", cls.min_box_area_px))),
            mask_encoding=str(data.get("mask_encoding", cls.mask_encoding)).lower(),
            fallback_box_mask=bool(data.get("fallback_box_mask", cls.fallback_box_mask)),
            sam2=Sam2Config.from_dict(data.get("sam2") if isinstance(data.get("sam2"), dict) else {}),
        )
        if cfg.mask_encoding not in {"rle", "polygon"}:
            cfg.mask_encoding = "rle"
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "device": self.device,
            "auto_load": self.auto_load,
            "fail_open": self.fail_open,
            "max_masks_per_frame": self.max_masks_per_frame,
            "min_box_area_px": self.min_box_area_px,
            "mask_encoding": self.mask_encoding,
            "fallback_box_mask": self.fallback_box_mask,
            "sam2": {
                "checkpoint_path": self.sam2.checkpoint_path,
                "model_config": self.sam2.model_config,
            },
        }


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_segmentation_config(overrides: dict[str, Any] | None = None) -> SegmentationConfig:
    if overrides is not None:
        return SegmentationConfig.from_dict(overrides)
    try:
        from inference.config_runtime import load_runtime_config

        return SegmentationConfig.from_dict(load_runtime_config("segmentation"))
    except FileNotFoundError:
        return SegmentationConfig()
