#!/usr/bin/env python3
"""Smoke test for the VideoMAE anomaly detection adapter.

Loads the PretrainedVideoAdapter, constructs synthetic 16-frame clips,
runs inference, and validates that scores are in [0, 1] range.

Usage:
  python scripts/smoke_anomaly_videomae.py
  python scripts/smoke_anomaly_videomae.py --model-path models/anomaly/current
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_MODEL_PATH = str(ROOT / "models" / "anomaly" / "current")


def _make_clip(num_frames: int = 16, w: int = 224, h: int = 224, seed: int = 0):
    import numpy as np
    rng = np.random.default_rng(seed)
    return [
        rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
        for _ in range(num_frames)
    ]


def _load_video_clip(video_path: str, num_frames: int = 16):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    frames = []
    while len(frames) < num_frames:
        ok, frame = cap.read()
        if not ok:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame_rgb)
    cap.release()

    if not frames:
        raise RuntimeError(f"No frames decoded from video: {video_path}")

    if len(frames) < num_frames:
        frames.extend([frames[-1]] * (num_frames - len(frames)))
    else:
        indices = np.linspace(0, len(frames) - 1, num_frames, dtype=int)
        frames = [frames[i] for i in indices]
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--video", default=None, help="Optional test video path for real decode smoke")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--num-clips", type=int, default=2)
    args = parser.parse_args()

    print("=" * 60)
    print("VideoMAE Anomaly Adapter Smoke Test")
    print("=" * 60)
    print(f"\n  Model path : {args.model_path}")
    print(f"  Video      : {args.video if args.video else '(synthetic clips)'}")
    print(f"  Device     : {args.device}")

    if not Path(args.model_path).exists():
        print(f"\n  ERROR: Model path not found: {args.model_path}", file=sys.stderr)
        sys.exit(1)

    from inference.anomaly.pretrained_adapter import PretrainedVideoAdapter

    print(f"\n[Loading VideoMAE adapter...]")
    t0 = time.monotonic()
    adapter = PretrainedVideoAdapter(model_path=args.model_path, device=args.device)
    adapter.load()
    load_time = time.monotonic() - t0

    health = adapter.health()
    print(f"  Load time  : {load_time:.2f}s")
    print(f"  Status     : {health['status']}")
    print(f"  Loaded     : {health['loaded']}")
    if not adapter.is_loaded():
        print(f"\n  ERROR: Adapter failed to load.", file=sys.stderr)
        print(f"  Health: {health}", file=sys.stderr)
        sys.exit(1)

    print(f"  Device     : {health.get('device')}")
    print(f"  Num classes: {health.get('num_classes')}")

    source_label = "video clip(s)" if args.video else "synthetic clip(s)"
    print(f"\n[Running inference on {args.num_clips} {source_label}...]")
    all_pass = True
    for i in range(args.num_clips):
        if args.video:
            video_path = args.video
            if not Path(video_path).is_absolute():
                video_path = str(ROOT / video_path)
            if not Path(video_path).exists():
                print(f"  Clip {i+1}: FAIL — video not found: {video_path}", file=sys.stderr)
                all_pass = False
                continue
            try:
                frames = _load_video_clip(video_path, num_frames=16)
            except Exception as exc:
                print(f"  Clip {i+1}: FAIL — video decode error: {exc}", file=sys.stderr)
                all_pass = False
                continue
        else:
            frames = _make_clip(num_frames=16, seed=i)
        t1 = time.monotonic()
        pred = adapter.predict_clip(
            frames=frames,
            metadata={"camera_id": f"smoke_cam_{i}", "window_seconds": 5.0},
        )
        infer_ms = (time.monotonic() - t1) * 1000

        if pred is None:
            print(f"  Clip {i+1}: FAIL — predict_clip returned None", file=sys.stderr)
            all_pass = False
            continue

        score_ok = 0.0 <= pred.score <= 1.0
        status_str = "PASS" if score_ok else "FAIL"
        if not score_ok:
            all_pass = False
        print(
            f"  Clip {i+1}: {status_str} — score={pred.score:.4f}  severity={pred.severity}  "
            f"type={pred.anomaly_type}  inference={infer_ms:.0f}ms"
        )

    print(f"\n{'=' * 60}")
    if all_pass:
        print(f"RESULT: PASS")
        print(f"  VideoMAE adapter loaded and ran inference without error.")
        print(f"  Load: {load_time:.2f}s  |  All clips: score in [0,1] validated.")
    else:
        print(f"RESULT: FAIL — one or more clips did not produce valid predictions")
        sys.exit(1)
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
