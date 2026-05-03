"""
Entry point for YOLO fine-tuning.

Usage:
    python ml/training/train.py ml/configs/weapon.yaml
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root without installing as a package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ultralytics import YOLO

from ml.training.config_loader import TrainingConfig, load_config
from ml.training.utils import get_logger, validate_path, validate_dataset


def run_training(config_path: str) -> Path:
    """
    Load config, validate dataset, run YOLO training, save metrics.

    Returns the experiment output directory.
    """
    config = load_config(config_path)

    # Auto-generated versioned experiment name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned_name = f"{config.experiment_name}_v{timestamp}"

    output_dir = Path(config.output_path) / versioned_name
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = get_logger(versioned_name, log_dir=str(output_dir))
    logger.info(f"Experiment: {versioned_name}")
    logger.info(f"Config: {config_path}")
    logger.info(f"Output dir: {output_dir}")

    # Validate inputs
    validate_path(config.dataset_path, must_be_file=True, label="dataset_path")
    logger.info("Validating dataset ...")
    validate_dataset(config.dataset_path)
    logger.info("Dataset validation passed.")

    model_path = validate_path(config.model, must_be_file=True, label="model")
    logger.info(f"Loading model: {model_path}")
    model = YOLO(str(model_path))

    logger.info(
        f"Starting training: epochs={config.epochs}, "
        f"batch={config.batch_size}, imgsz={config.img_size}"
    )

    results = model.train(
        data=config.dataset_path,
        epochs=config.epochs,
        batch=config.batch_size,
        imgsz=config.img_size,
        project=str(output_dir),
        name="weights",
        exist_ok=True,
        verbose=True,
    )

    # Locate saved weights
    weights_dir = output_dir / "weights"
    best_pt  = weights_dir / "best.pt"
    last_pt  = weights_dir / "last.pt"

    # Extract metrics safely
    metrics_data: dict = {}
    try:
        if hasattr(results, "results_dict"):
            metrics_data = {k: float(v) for k, v in results.results_dict.items()}
    except Exception:
        pass

    # Save metrics.json
    metrics = {
        "experiment": versioned_name,
        "timestamp": timestamp,
        "config": {
            "dataset_path": config.dataset_path,
            "epochs": config.epochs,
            "batch_size": config.batch_size,
            "img_size": config.img_size,
            "model": config.model,
        },
        "outputs": {
            "best_model": str(best_pt) if best_pt.exists() else None,
            "last_model": str(last_pt) if last_pt.exists() else None,
        },
        "metrics": metrics_data,
    }

    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    logger.info(f"Metrics saved: {metrics_path}")
    logger.info(f"Best weights:  {best_pt}")
    logger.info(f"Last weights:  {last_pt}")
    logger.info("Training complete.")

    return output_dir


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python ml/training/train.py <config.yaml>")
        sys.exit(1)
    run_training(sys.argv[1])
