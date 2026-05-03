import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

_EXPORTS_DEFAULT = os.path.join(ROOT, "models", "exports")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sentinel AI — Export trained YOLOv8 model to ONNX",
        add_help=True,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--weights",
        required=True,
        help="Path to trained model weights (.pt)",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Export name used in output filename: {name}_best.onnx",
    )
    parser.add_argument(
        "--output-dir",
        default=_EXPORTS_DEFAULT,
        dest="output_dir",
        help="Directory to save ONNX file (default: %(default)s)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Export image size (default: %(default)s)",
    )
    return parser


def main(args: argparse.Namespace) -> None:
    if not Path(args.weights).exists():
        print(f"[ERROR] Weights not found: {args.weights}")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 60)
    print("  Sentinel AI — ONNX Export")
    print("=" * 60)
    print(f"  weights:    {args.weights}")
    print(f"  name:       {args.name}")
    print(f"  output_dir: {args.output_dir}")
    print(f"  imgsz:      {args.imgsz}")
    print("=" * 60)

    model = YOLO(args.weights)
    model.export(format="onnx", imgsz=args.imgsz, dynamic=False, simplify=True)

    # Ultralytics writes <weights_stem>.onnx next to the .pt file
    onnx_src = Path(args.weights).with_suffix(".onnx")
    if not onnx_src.exists():
        print(
            f"[ERROR] Expected ONNX output not found: {onnx_src}\n"
            f"        Check {Path(args.weights).parent} for the exported file."
        )
        sys.exit(1)

    onnx_dst = Path(args.output_dir) / f"{args.name}_best.onnx"
    shutil.copy2(onnx_src, onnx_dst)

    print(f"\n[OK] Exported: {onnx_dst}")
    print("=" * 60)


if __name__ == "__main__":
    _parser = build_parser()
    _args = _parser.parse_args()
    main(_args)
