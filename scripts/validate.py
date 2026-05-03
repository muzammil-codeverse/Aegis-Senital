import sys
import argparse
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO

DEFAULT_WEAPON_MODEL = "/content/sentinel-ai-system/models/weapon_detect/weights/best.pt"
DEFAULT_PHONE_MODEL = "/content/sentinel-ai-system/models/phone_detect/weights/best.pt"
DEFAULT_WEAPON_CONFIG = "/content/sentinel-ai-system/configs/weapon.yaml"
DEFAULT_PHONE_CONFIG = "/content/sentinel-ai-system/configs/phone.yaml"


def validate_model(model_path: str, data_config: str, label: str):
    print(f"\n=== Validating: {label} ===")
    if not Path(model_path).exists():
        print(f"[ERROR] Model not found: {model_path}")
        sys.exit(1)

    model = YOLO(model_path)
    metrics = model.val(data=data_config, verbose=True)

    print(f"\n--- {label} Results ---")
    print(f"mAP@0.5:      {metrics.box.map50:.4f}")
    print(f"mAP@0.5:0.95: {metrics.box.map:.4f}")
    print(f"Precision:    {metrics.box.mp:.4f}")
    print(f"Recall:       {metrics.box.mr:.4f}")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Validate trained YOLOv8 models")
    parser.add_argument(
        "--model",
        choices=["weapon", "phone", "both"],
        default="both",
        help="Which model to validate (default: both)",
    )
    args = parser.parse_args()

    if args.model in ("weapon", "both"):
        validate_model(DEFAULT_WEAPON_MODEL, DEFAULT_WEAPON_CONFIG, "Weapon Detection")

    if args.model in ("phone", "both"):
        validate_model(DEFAULT_PHONE_MODEL, DEFAULT_PHONE_CONFIG, "Phone Detection")

    print("\n=== Validation Complete ===")


if __name__ == "__main__":
    main()
