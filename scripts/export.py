import sys
import argparse
import shutil
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO

EXPORTS_DIR = "/content/sentinel-ai-system/models/exports"

MODEL_PATHS = {
    "weapon": "/content/sentinel-ai-system/models/weapon_detect/weights/best.pt",
    "phone": "/content/sentinel-ai-system/models/phone_detect/weights/best.pt",
}


def export_model(name: str, model_path: str, exports_dir: str):
    print(f"\n=== Exporting: {name} ===")
    if not Path(model_path).exists():
        print(f"[ERROR] Model not found: {model_path}")
        sys.exit(1)

    Path(exports_dir).mkdir(parents=True, exist_ok=True)

    model = YOLO(model_path)
    model.export(format="onnx", imgsz=640, dynamic=False, simplify=True)

    onnx_src = Path(model_path).with_suffix(".onnx")
    if not onnx_src.exists():
        onnx_src = Path(model_path).parent / (Path(model_path).stem + ".onnx")

    onnx_dst = Path(exports_dir) / f"{name}_best.onnx"
    if onnx_src.exists():
        shutil.copy2(onnx_src, onnx_dst)
        print(f"[OK] Exported to: {onnx_dst}")
    else:
        print(f"[WARN] ONNX file not found at expected path: {onnx_src}")
        print(f"       Check {Path(model_path).parent} for the exported file.")


def main():
    parser = argparse.ArgumentParser(description="Export trained YOLOv8 models to ONNX")
    parser.add_argument(
        "--model",
        choices=["weapon", "phone", "both"],
        default="both",
        help="Which model to export (default: both)",
    )
    args = parser.parse_args()

    targets = list(MODEL_PATHS.keys()) if args.model == "both" else [args.model]

    for name in targets:
        export_model(name, MODEL_PATHS[name], EXPORTS_DIR)

    print(f"\n=== Export Complete — files in {EXPORTS_DIR} ===")


if __name__ == "__main__":
    main()
