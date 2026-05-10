#!/usr/bin/env python3
"""Smoke test for the Open-Vocab (GroundingDINO) runtime adapter.

Loads the GroundingDINO adapter using the local model path from
configs/runtime/open_vocab.yaml (or AEGIS_OPEN_VOCAB_MODEL_PATH env var),
runs a single detection pass, and reports results.

Usage:
  python scripts/smoke_open_vocab_runtime.py
  python scripts/smoke_open_vocab_runtime.py --image storage/test_outputs/sam_smoke.jpg
  python scripts/smoke_open_vocab_runtime.py --image path/to/any/image.jpg --prompts "weapon" "knife" "person"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

CONFIG_PATH = ROOT / "configs" / "runtime" / "open_vocab.yaml"
DEFAULT_PROMPTS = ["weapon", "knife", "gun", "phone", "suspicious object"]


def _load_open_vocab_config() -> dict:
    try:
        import yaml
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        return raw
    except Exception as exc:
        print(f"  WARN: Could not load open_vocab.yaml: {exc}", file=sys.stderr)
        return {}


def _get_model_path(config: dict) -> str | None:
    env_path = os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path
    cfg_path = config.get("model", {}).get("local_model_path", "")
    if cfg_path:
        full = ROOT / cfg_path if not Path(cfg_path).is_absolute() else Path(cfg_path)
        if full.exists():
            return str(full)
        if Path(cfg_path).exists():
            return cfg_path
    return None


def _make_test_image() -> str:
    """Generate a minimal synthetic test image if none provided."""
    import numpy as np
    try:
        from PIL import Image
        arr = np.full((480, 640, 3), (120, 110, 90), dtype=np.uint8)
        arr[200:320, 280:360] = (60, 100, 180)  # blue rectangle = "person"
        arr[350:400, 260:310] = (80, 60, 40)    # brown rectangle = "bag"
        img = Image.fromarray(arr)
        out = ROOT / "storage" / "test_outputs" / "open_vocab_smoke.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return str(out)
    except Exception as exc:
        print(f"  WARN: PIL unavailable ({exc}), using numpy array directly", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=str, default=None, help="Path to test image (default: auto-generate)")
    parser.add_argument("--prompts", nargs="+", default=DEFAULT_PROMPTS)
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    args = parser.parse_args()

    print("=" * 60)
    print("Open-Vocab (GroundingDINO) Smoke Test")
    print("=" * 60)

    # Load config
    config = _load_open_vocab_config()
    model_path = _get_model_path(config)

    print(f"\n[Config]")
    if model_path:
        print(f"  Model path : {model_path}")
    else:
        env_path = os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
        cfg_path = config.get("model", {}).get("local_model_path", "")
        print(f"  WARN: Model path not found.")
        if env_path:
            print(f"    AEGIS_OPEN_VOCAB_MODEL_PATH={env_path!r} (path does not exist)")
        if cfg_path:
            print(f"    config local_model_path={cfg_path!r} (resolved: {ROOT / cfg_path})")
        if not env_path and not cfg_path:
            print(f"    Neither env var nor config local_model_path is set.")
        print(f"\n  Run: python scripts/setup_open_vocab_model.py  to download the model first.")
        sys.exit(1)

    print(f"  Prompts    : {args.prompts}")
    print(f"  Box thresh : {args.box_threshold}")
    print(f"  Text thresh: {args.text_threshold}")

    # Resolve test image
    if args.image:
        image_path = args.image
        if not Path(image_path).is_absolute():
            image_path = str(ROOT / image_path)
        if not Path(image_path).exists():
            print(f"\n  ERROR: Image not found: {image_path}", file=sys.stderr)
            sys.exit(1)
    else:
        image_path = _make_test_image()
        if image_path is None:
            print("\n  ERROR: Could not generate test image. Pass --image <path>.", file=sys.stderr)
            sys.exit(1)
        print(f"  Image      : {image_path} (synthetic)")

    print(f"\n[Loading GroundingDINO adapter...]")
    t0 = time.monotonic()

    # Build adapter config matching open_vocab.yaml structure
    adapter_config = {
        "model": {
            "provider": "grounding_dino",
            "model_id": "grounding_dino_base",
            "device_preference": "cuda",
            "local_model_path": model_path,
            "local_processor_path": model_path,
        }
    }

    try:
        from inference.open_vocab.grounding_dino_adapter import GroundingDINOAdapter
        adapter = GroundingDINOAdapter(config=adapter_config)
        adapter.load()
    except Exception as exc:
        print(f"  ERROR: Failed to import/construct adapter: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    load_time = time.monotonic() - t0

    if not adapter.is_available():
        status = adapter.get_status()
        print(f"  ERROR: Adapter not available after load: {status.get('reason')}", file=sys.stderr)
        sys.exit(1)

    print(f"  Loaded in {load_time:.2f}s on {adapter._device}")

    # Run detection
    print(f"\n[Running detection on: {Path(image_path).name}]")
    t1 = time.monotonic()
    try:
        detections = adapter.detect(
            image=image_path,
            prompts=args.prompts,
            thresholds={
                "box_threshold": args.box_threshold,
                "text_threshold": args.text_threshold,
            },
        )
    except Exception as exc:
        print(f"  ERROR: Detection failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    infer_time = time.monotonic() - t1

    print(f"  Inference time : {infer_time*1000:.1f} ms")
    print(f"  Detections     : {len(detections)}")

    if detections:
        print(f"\n  Results:")
        for i, det in enumerate(detections):
            print(f"    [{i+1}] label={det['label']!r:20s} conf={det['confidence']:.3f}  bbox={det['bbox']}")
    else:
        print(f"\n  No detections above threshold (this is normal for a synthetic image).")
        print(f"  The adapter is functional — detection ran without error.")

    # Status summary
    status = adapter.get_status()
    print(f"\n[Status]")
    for k, v in status.items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 60}")
    print(f"RESULT: PASS")
    print(f"  GroundingDINO adapter loaded and ran detection without error.")
    print(f"  Load: {load_time:.2f}s  |  Inference: {infer_time*1000:.1f}ms  |  Detections: {len(detections)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
