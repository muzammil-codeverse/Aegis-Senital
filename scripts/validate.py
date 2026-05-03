import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import argparse
from pathlib import Path

from ultralytics import YOLO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sentinel AI — Validate trained YOLOv8 model (mAP, precision, recall)",
        add_help=True,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--weights",
        required=True,
        help="Path to trained model weights (.pt or .onnx)",
    )
    parser.add_argument(
        "--data",
        default=os.path.join(ROOT, "configs", "weapon.yaml"),
        help="Path to YOLO dataset YAML (default: configs/weapon.yaml inside repo root)",
    )
    return parser


def main(args: argparse.Namespace) -> None:
    if not Path(args.weights).exists():
        print(f"[ERROR] Weights not found: {args.weights}")
        sys.exit(1)
    if not Path(args.data).exists():
        print(f"[ERROR] Dataset config not found: {args.data}")
        sys.exit(1)

    print("=" * 60)
    print("  Sentinel AI — Model Validation")
    print("=" * 60)
    print(f"  weights: {args.weights}")
    print(f"  data:    {args.data}")
    print("=" * 60)

    model = YOLO(args.weights)
    metrics = model.val(data=args.data, verbose=True)

    print("\n" + "=" * 60)
    print("  Validation Results")
    print("=" * 60)
    print(f"  mAP@0.5:        {metrics.box.map50:.4f}")
    print(f"  mAP@0.5:0.95:   {metrics.box.map:.4f}")
    print(f"  Precision:      {metrics.box.mp:.4f}")
    print(f"  Recall:         {metrics.box.mr:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    _parser = build_parser()
    _args = _parser.parse_args()
    main(_args)
