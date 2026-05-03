import sys
import argparse
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO
from utils.data_check import validate_splits

_COLAB_ROOT = "/content/sentinel-ai-system"
_COLAB_DATASETS = "/content/datasets"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train YOLOv8n weapon detection model"
    )
    parser.add_argument(
        "--data",
        default=f"{_COLAB_ROOT}/configs/weapon.yaml",
        help="Path to YOLO dataset YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--label-dir",
        default=f"{_COLAB_DATASETS}/weapon/labels",
        help="Root labels directory; must contain train/ and val/ subdirs (default: %(default)s)",
    )
    parser.add_argument(
        "--epochs", type=int, default=40,
        help="Number of training epochs (default: %(default)s)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Input image size (default: %(default)s)",
    )
    parser.add_argument(
        "--batch", type=int, default=16,
        help="Batch size (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=f"{_COLAB_ROOT}/models",
        help="Directory for model artifacts (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip label validation (not recommended)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=== Weapon Detection Training ===")
    print(f"  data:    {args.data}")
    print(f"  epochs:  {args.epochs}")
    print(f"  imgsz:   {args.imgsz}")
    print(f"  batch:   {args.batch}")
    print(f"  output:  {args.output}")

    if not args.skip_validation:
        print("\nValidating labels ...")
        validate_splits(args.label_dir, splits=("train", "val"))
        print("Labels OK.\n")

    Path(args.output).mkdir(parents=True, exist_ok=True)

    model = YOLO("yolov8n.pt")
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.output,
        name="weapon_detect",
        exist_ok=True,
        verbose=True,
    )

    print(f"\n=== Training Complete ===")
    print(f"Artifacts: {args.output}/weapon_detect")


if __name__ == "__main__":
    main()
