import sys
import argparse
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO

_COLAB_ROOT = "/content/sentinel-ai-system"

_DEFAULT_WEAPON_MODEL = f"{_COLAB_ROOT}/models/weapon_detect/weights/best.pt"
_DEFAULT_PHONE_MODEL = f"{_COLAB_ROOT}/models/phone_detect/weights/best.pt"
_DEFAULT_WEAPON_CONFIG = f"{_COLAB_ROOT}/configs/weapon.yaml"
_DEFAULT_PHONE_CONFIG = f"{_COLAB_ROOT}/configs/phone.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate trained YOLOv8 models — prints mAP, precision, recall"
    )
    parser.add_argument(
        "--model",
        choices=["weapon", "phone", "both"],
        default="both",
        help="Which model to validate (default: both)",
    )
    parser.add_argument(
        "--weapon-model",
        default=_DEFAULT_WEAPON_MODEL,
        help="Path to trained weapon model (default: %(default)s)",
    )
    parser.add_argument(
        "--phone-model",
        default=_DEFAULT_PHONE_MODEL,
        help="Path to trained phone model (default: %(default)s)",
    )
    parser.add_argument(
        "--weapon-config",
        default=_DEFAULT_WEAPON_CONFIG,
        help="Weapon dataset YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--phone-config",
        default=_DEFAULT_PHONE_CONFIG,
        help="Phone dataset YAML (default: %(default)s)",
    )
    return parser.parse_args()


def validate_model(label: str, model_path: str, data_config: str) -> None:
    print(f"\n=== Validating: {label} ===")
    if not Path(model_path).exists():
        print(f"[ERROR] Model not found: {model_path}")
        sys.exit(1)
    if not Path(data_config).exists():
        print(f"[ERROR] Dataset config not found: {data_config}")
        sys.exit(1)

    model = YOLO(model_path)
    metrics = model.val(data=data_config, verbose=True)

    print(f"\n--- {label} Results ---")
    print(f"  mAP@0.5:        {metrics.box.map50:.4f}")
    print(f"  mAP@0.5:0.95:   {metrics.box.map:.4f}")
    print(f"  Precision:      {metrics.box.mp:.4f}")
    print(f"  Recall:         {metrics.box.mr:.4f}")


def main() -> None:
    args = parse_args()

    if args.model in ("weapon", "both"):
        validate_model("Weapon Detection", args.weapon_model, args.weapon_config)

    if args.model in ("phone", "both"):
        validate_model("Phone Detection", args.phone_model, args.phone_config)

    print("\n=== Validation Complete ===")


if __name__ == "__main__":
    main()
