from __future__ import annotations

from pathlib import Path

import scripts.validate_runtime as validate_runtime


def test_production_enabled_missing_sam2_assets_fail_validation(tmp_path, monkeypatch) -> None:
    root = tmp_path
    config_path = root / "configs" / "runtime" / "segmentation.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
segmentation:
  enabled: true
  provider: sam2
  sam2:
    checkpoint_path: models/segmentation/sam2/checkpoint.pt
    model_config: configs/segmentation/sam2.yaml
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_runtime, "ROOT", root)
    monkeypatch.setattr(validate_runtime, "_try_import", lambda module: False)

    policy = {
        "feature_dependencies": {
            "segmentation": {
                "label": "SAM2 segmentation",
                "module": "sam2",
                "config_path": "configs/runtime/segmentation.yaml",
                "enabled_path": "segmentation.enabled",
                "provider_path": "segmentation.provider",
                "checkpoint_path": "models/segmentation/sam2/checkpoint.pt",
                "model_config": "configs/segmentation/sam2.yaml",
            }
        }
    }

    results = validate_runtime.validate_feature_dependencies(policy, "production")

    required_failures = [item for item in results if item["required"] and not item["ok"]]
    assert required_failures
    assert {item["name"] for item in required_failures} >= {
        "SAM2 segmentation",
        "SAM2 checkpoint",
        "SAM2 model config",
    }


def test_development_enabled_missing_sam2_assets_warns(tmp_path, monkeypatch) -> None:
    root = tmp_path
    config_path = root / "configs" / "runtime" / "segmentation.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("segmentation:\n  enabled: true\n  provider: sam2\n", encoding="utf-8")
    monkeypatch.setattr(validate_runtime, "ROOT", root)
    monkeypatch.setattr(validate_runtime, "_try_import", lambda module: False)
    policy = {
        "feature_dependencies": {
            "segmentation": {
                "label": "SAM2 segmentation",
                "module": "sam2",
                "config_path": "configs/runtime/segmentation.yaml",
                "enabled_path": "segmentation.enabled",
                "provider_path": "segmentation.provider",
            }
        }
    }

    results = validate_runtime.validate_feature_dependencies(policy, "development")

    assert any(item["status"] == "WARN" for item in results)
    assert not any(item["required"] and not item["ok"] for item in results)
