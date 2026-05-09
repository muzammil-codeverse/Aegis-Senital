from __future__ import annotations

from pathlib import Path

import pytest


def test_local_override_merges_machine_specific_paths(tmp_path: Path):
    from backend.app.evaluation.benchmark_config import load_evaluation_config

    base = tmp_path / "evaluation.yaml"
    local = tmp_path / "evaluation.local.yaml"
    base.write_text(
        """
models:
  weapon_yolov8_baseline:
    path: models/weapon/model.pt
datasets:
  weapon_eval:
    type: coco_yolo
    images_dir: datasets/evaluation/weapon/images
    labels_dir: datasets/evaluation/weapon/labels
""".strip(),
        encoding="utf-8",
    )
    local.write_text(
        """
models:
  weapon_yolov8_baseline:
    path: D:/machine-specific/weapon.pt
datasets:
  weapon_eval:
    images_dir: D:/datasets/weapon/images
    labels_dir: D:/datasets/weapon/labels
""".strip(),
        encoding="utf-8",
    )

    merged = load_evaluation_config(base)

    assert merged["models"]["weapon_yolov8_baseline"]["path"] == "D:/machine-specific/weapon.pt"
    assert merged["datasets"]["weapon_eval"]["images_dir"] == "D:/datasets/weapon/images"
    assert merged["datasets"]["weapon_eval"]["labels_dir"] == "D:/datasets/weapon/labels"


def test_missing_model_path_reports_exact_path():
    from backend.app.evaluation.model_resolver import resolve_adapter

    missing_path = "D:/does-not-exist/weapon_candidate.pt"
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_adapter(
            {
                "name": "weapon_yolov8_baseline",
                "backend": "ultralytics_yolo",
                "path": missing_path,
                "required": True,
                "classes": ["weapon"],
            },
            device="cpu",
        )

    assert missing_path in str(exc_info.value)


def test_missing_dataset_path_reports_exact_path():
    from backend.app.evaluation.datasets.dataset_registry import DatasetRegistry

    config = {
        "datasets": {
            "weapon_eval": {
                "task": "detection",
                "type": "coco_yolo",
                "images_dir": "D:/missing/weapon/images",
                "labels_dir": "D:/missing/weapon/labels",
                "required": True,
                "class_names": ["weapon"],
            }
        }
    }
    registry = DatasetRegistry(config)

    with pytest.raises(FileNotFoundError) as exc_info:
        registry.get_required("weapon_eval")

    message = str(exc_info.value)
    assert "D:/missing/weapon/images" in message
    assert "D:/missing/weapon/labels" in message
