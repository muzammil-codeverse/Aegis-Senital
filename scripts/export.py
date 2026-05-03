import sys
import argparse
import shutil
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO

_COLAB_ROOT = "/content/sentinel-ai-system"

_DEFAULT_MODEL_PATHS: dict[str, str] = {
    "weapon": f"{_COLAB_ROOT}/models/weapon_detect/weights/best.pt",
    "phone": f"{_COLAB_ROOT}/models/phone_detect/weights/best.pt",
}
_DEFAULT_EXPORTS_DIR = f"{_COLAB_ROOT}/models/exports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export trained YOLOv8 models to ONNX format"
    )
    parser.add_argument(
        "--model",
        choices=["weapon", "phone", "both"],
        default="both",
        help="Which model to export (default: both)",
    )
    parser.add_argument(
        "--weapon-model",
        default=_DEFAULT_MODEL_PATHS["weapon"],
        help="Path to trained weapon model .pt (default: %(default)s)",
    )
    parser.add_argument(
        "--phone-model",
        default=_DEFAULT_MODEL_PATHS["phone"],
        help="Path to trained phone model .pt (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default=_DEFAULT_EXPORTS_DIR,
        help="Directory to save exported ONNX files (default: %(default)s)",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Export image size (default: %(default)s)",
    )
    return parser.parse_args()


def export_model(name: str, model_path: str, output_dir: str, imgsz: int) -> None:
    print(f"\n=== Exporting: {name} ===")

    if not Path(model_path).exists():
        print(f"[ERROR] Model weights not found: {model_path}")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    model = YOLO(model_path)
    model.export(format="onnx", imgsz=imgsz, dynamic=False, simplify=True)

    # Ultralytics always writes <stem>.onnx alongside the .pt file
    onnx_src = Path(model_path).with_suffix(".onnx")
    if not onnx_src.exists():
        print(
            f"[ERROR] Expected ONNX output not found: {onnx_src}\n"
            f"        Check {Path(model_path).parent} for the exported file."
        )
        sys.exit(1)

    onnx_dst = Path(output_dir) / f"{name}_best.onnx"
    shutil.copy2(onnx_src, onnx_dst)
    print(f"[OK] {onnx_dst}")


def main() -> None:
    args = parse_args()

    model_map = {
        "weapon": args.weapon_model,
        "phone": args.phone_model,
    }
    targets = list(model_map.keys()) if args.model == "both" else [args.model]

    for name in targets:
        export_model(name, model_map[name], args.output_dir, args.imgsz)

    print(f"\n=== Export Complete — files in {args.output_dir} ===")


if __name__ == "__main__":
    main()
