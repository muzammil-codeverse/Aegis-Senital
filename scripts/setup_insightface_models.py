"""
Download and cache InsightFace model bundles into a local models directory.
Run once before production deployment. Never runs during inference startup.

Usage:
    python scripts/setup_insightface_models.py --model buffalo_l --target models/buffalo_l
"""

import argparse
import os
import shutil
import sys
from pathlib import Path


def download_and_install(model_name: str, target_dir: Path) -> None:
    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        print("ERROR: insightface is not installed. Run: pip install insightface", file=sys.stderr)
        sys.exit(1)

    # InsightFace downloads models into <root>/models/<name>
    # We use a temporary local root, then optionally copy to target_dir
    local_root = Path("models")
    cache_model_dir = local_root / "models" / model_name  # insightface internal path

    print(f"Initializing InsightFace FaceAnalysis with model={model_name}, root={local_root}")

    # Determine ONNX provider — try CUDA first, fall back to CPU
    providers = []
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            print("ONNX provider: CUDAExecutionProvider (GPU)")
        else:
            providers = ["CPUExecutionProvider"]
            print("WARNING: CUDAExecutionProvider not available. Using CPUExecutionProvider.")
    except ImportError:
        providers = ["CPUExecutionProvider"]
        print("WARNING: onnxruntime not found; InsightFace will use its default provider.")

    try:
        app = FaceAnalysis(name=model_name, root=str(local_root), providers=providers)
        app.prepare(ctx_id=0, det_size=(640, 640))
        print(f"InsightFace {model_name} loaded successfully via FaceAnalysis.prepare()")
    except Exception as exc:
        print(f"ERROR during FaceAnalysis.prepare(): {exc}", file=sys.stderr)
        # Still check if files were downloaded before erroring out
        if not cache_model_dir.exists():
            sys.exit(1)
        print("Model files may still have been downloaded; continuing.")

    # Discover where InsightFace actually wrote the files
    # InsightFace stores models in: <root>/models/<name>/
    search_dirs = [
        local_root / "models" / model_name,
        Path.home() / ".insightface" / "models" / model_name,
    ]

    source_dir: Path | None = None
    for candidate in search_dirs:
        if candidate.exists() and any(candidate.iterdir()):
            source_dir = candidate
            break

    if source_dir is None:
        print(f"ERROR: Could not locate downloaded model files for {model_name}.", file=sys.stderr)
        print("Searched:", [str(d) for d in search_dirs], file=sys.stderr)
        sys.exit(1)

    print(f"Model files found at: {source_dir}")

    # If target_dir differs from source_dir, copy files there
    target_dir = target_dir.resolve()
    if source_dir.resolve() != target_dir:
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.iterdir():
            dest = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        print(f"Copied model files to: {target_dir}")
    else:
        print(f"Model already in target directory: {target_dir}")

    # Report installed files
    print("\nInstalled files:")
    for f in sorted(target_dir.rglob("*")):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.relative_to(target_dir)}  ({size_mb:.2f} MB)")

    print(f"\nInsightFace {model_name} installation complete.")
    print("Verification command:")
    print(
        f"  python -c \"from insightface.app import FaceAnalysis; "
        f"app=FaceAnalysis(name='{model_name}', root='models'); "
        f"app.prepare(ctx_id=0, det_size=(640,640)); print('InsightFace {model_name} OK')\""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download InsightFace model bundles into local models directory")
    parser.add_argument("--model", default="buffalo_l", help="InsightFace model name (default: buffalo_l)")
    parser.add_argument("--target", default="models/buffalo_l", help="Target directory for model files")
    args = parser.parse_args()

    target = Path(args.target)
    print(f"Setting up InsightFace model: {args.model} -> {target}")
    download_and_install(args.model, target)


if __name__ == "__main__":
    main()
