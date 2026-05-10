#!/usr/bin/env python3
"""Download or generate safe sample test videos for end-to-end pipeline validation.

Supports three providers:
  pexels    — Pexels video API (requires PEXELS_API_KEY env var)
  pixabay   — Pixabay video API (requires PIXABAY_API_KEY env var)
  synthetic — generate videos locally with OpenCV (no key needed)

Usage:
  python scripts/download_test_videos.py --provider synthetic
  python scripts/download_test_videos.py --provider pexels --queries "pedestrians" "traffic" --max-per-query 1
  python scripts/download_test_videos.py --provider pixabay --queries "street people" --max-per-query 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "datasets" / "test_videos"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Synthetic video generator
# ---------------------------------------------------------------------------

def _generate_synthetic_videos(queries: list[str], max_per_query: int) -> list[dict]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("ERROR: opencv-python / numpy not installed", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    video_id = len(list(OUTPUT_DIR.glob("*.mp4")))

    scenes = {
        "pedestrians walking street": _scene_pedestrians,
        "crowd walking": _scene_crowd,
        "person running": _scene_running,
        "traffic road": _scene_traffic,
        "bag backpack scene": _scene_bag,
        "general cctv street scene": _scene_cctv,
    }

    for query in queries:
        for _ in range(max_per_query):
            scene_fn = None
            for key, fn in scenes.items():
                if any(word in query.lower() for word in key.split()):
                    scene_fn = fn
                    break
            scene_fn = scene_fn or _scene_pedestrians

            video_id += 1
            vid_id = f"test_{video_id:03d}"
            out_path = OUTPUT_DIR / f"{vid_id}.mp4"

            print(f"  Generating synthetic video: {out_path.name} (query: {query!r})")
            _write_synthetic_video(out_path, scene_fn, fps=15, duration_s=5)

            records.append({
                "video_id": vid_id,
                "source": "synthetic",
                "query": query,
                "file_path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
                "expected_content": ["person", "movement"],
                "expected_detections": ["person"],
                "notes": f"synthetic OpenCV video for functional testing — {query}",
            })

    return records


def _write_synthetic_video(path: Path, scene_fn, fps: int = 15, duration_s: int = 5) -> None:
    import cv2
    import numpy as np

    W, H = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (W, H))
    total_frames = fps * duration_s

    for frame_idx in range(total_frames):
        frame = scene_fn(frame_idx, total_frames, W, H)
        writer.write(frame)

    writer.release()


def _scene_pedestrians(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    frame = np.full((H, W, 3), (120, 100, 80), dtype=np.uint8)
    _draw_ground(frame, W, H)
    t = frame_idx / max(total - 1, 1)
    x = int(W * 0.1 + W * 0.8 * t)
    _draw_person(frame, x, H - 80, scale=1.0)
    _draw_person(frame, max(0, x - 100), H - 70, scale=0.85)
    return frame


def _scene_crowd(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    frame = np.full((H, W, 3), (100, 90, 80), dtype=np.uint8)
    _draw_ground(frame, W, H)
    t = frame_idx / max(total - 1, 1)
    for i in range(6):
        offset = (i * 80 + int(W * 0.05 * t * (1 + i % 2))) % (W - 60)
        _draw_person(frame, offset + 20, H - 60 - (i % 3) * 15, scale=0.7 + 0.1 * (i % 3))
    return frame


def _scene_running(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    frame = np.full((H, W, 3), (110, 130, 80), dtype=np.uint8)
    _draw_ground(frame, W, H)
    t = frame_idx / max(total - 1, 1)
    x = int(W * 0.05 + W * 0.9 * t)
    _draw_person(frame, x, H - 90, scale=1.1, running=True, frame_idx=frame_idx)
    return frame


def _scene_traffic(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    import cv2
    frame = np.full((H, W, 3), (60, 60, 70), dtype=np.uint8)
    cv2.rectangle(frame, (0, H // 2), (W, H), (80, 80, 80), -1)
    cv2.line(frame, (0, H * 2 // 3), (W, H * 2 // 3), (240, 220, 60), 3)
    t = frame_idx / max(total - 1, 1)
    car_x = int(-120 + (W + 240) * t)
    _draw_car(frame, car_x, H * 2 // 3 - 30)
    car_x2 = int(W + 80 - (W + 200) * t)
    _draw_car(frame, car_x2, H * 2 // 3 - 20, color=(30, 80, 200))
    return frame


def _scene_bag(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    frame = np.full((H, W, 3), (120, 110, 90), dtype=np.uint8)
    _draw_ground(frame, W, H)
    _draw_person(frame, 200, H - 80, scale=1.0)
    _draw_bag(frame, 250, H - 60)
    if frame_idx > total // 2:
        _draw_bag(frame, 265, H - 55)
    return frame


def _scene_cctv(frame_idx: int, total: int, W: int, H: int):
    import numpy as np
    import cv2
    frame = np.full((H, W, 3), (90, 85, 75), dtype=np.uint8)
    _draw_ground(frame, W, H)
    cv2.rectangle(frame, (0, 0), (W, H // 3), (70, 65, 55), -1)
    t = frame_idx / max(total - 1, 1)
    x1 = int(W * 0.1 + W * 0.3 * t)
    x2 = int(W * 0.7 - W * 0.2 * t)
    _draw_person(frame, x1, H - 75, scale=0.9)
    _draw_person(frame, x2, H - 65, scale=0.8)
    return frame


def _draw_ground(frame, W: int, H: int) -> None:
    import cv2
    cv2.rectangle(frame, (0, H - 40), (W, H), (100, 95, 85), -1)


def _draw_person(frame, cx: int, cy: int, scale: float = 1.0, running: bool = False, frame_idx: int = 0) -> None:
    import cv2
    import numpy as np
    s = scale
    # Head
    cv2.circle(frame, (cx, int(cy - 45 * s)), int(12 * s), (200, 170, 140), -1)
    # Body
    cv2.rectangle(frame, (int(cx - 10 * s), int(cy - 35 * s)), (int(cx + 10 * s), int(cy)), (60, 100, 180), -1)
    # Legs
    leg_offset = int(10 * np.sin(frame_idx * 0.5)) if running else 5
    cv2.line(frame, (cx, int(cy)), (int(cx - 8 * s), int(cy + 30 * s + leg_offset)), (40, 70, 140), int(4 * s))
    cv2.line(frame, (cx, int(cy)), (int(cx + 8 * s), int(cy + 30 * s - leg_offset)), (40, 70, 140), int(4 * s))


def _draw_car(frame, cx: int, cy: int, color=(180, 30, 30)) -> None:
    import cv2
    cv2.rectangle(frame, (cx, cy - 20), (cx + 100, cy), color, -1)
    cv2.rectangle(frame, (cx + 15, cy - 35), (cx + 85, cy - 20), color, -1)
    cv2.circle(frame, (cx + 20, cy + 5), 10, (30, 30, 30), -1)
    cv2.circle(frame, (cx + 80, cy + 5), 10, (30, 30, 30), -1)


def _draw_bag(frame, cx: int, cy: int) -> None:
    import cv2
    cv2.rectangle(frame, (cx, cy - 25), (cx + 30, cy), (80, 60, 40), -1)
    cv2.ellipse(frame, (cx + 15, cy - 25), (12, 5), 0, 0, 180, (70, 50, 30), 2)


# ---------------------------------------------------------------------------
# Pexels provider
# ---------------------------------------------------------------------------

def _download_pexels(queries: list[str], max_per_query: int) -> list[dict]:
    import requests

    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("ERROR: PEXELS_API_KEY not set. Use --provider synthetic instead.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    video_id = len(list(OUTPUT_DIR.glob("*.mp4")))
    headers = {"Authorization": api_key}

    for query in queries:
        url = "https://api.pexels.com/videos/search"
        params = {"query": query, "per_page": max_per_query, "orientation": "landscape", "size": "small"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  Pexels API error for {query!r}: {exc}", file=sys.stderr)
            continue

        for video in data.get("videos", [])[:max_per_query]:
            # Find smallest SD file
            files = sorted(video.get("video_files", []), key=lambda f: f.get("width", 9999))
            file_obj = next((f for f in files if f.get("width", 0) <= 1280), files[0] if files else None)
            if not file_obj:
                continue
            dl_url = file_obj.get("link")
            if not dl_url:
                continue

            video_id += 1
            vid_id = f"test_{video_id:03d}"
            out_path = OUTPUT_DIR / f"{vid_id}.mp4"
            print(f"  Downloading Pexels video: {out_path.name} ({query!r})")
            try:
                r = requests.get(dl_url, timeout=120, stream=True)
                r.raise_for_status()
                with open(out_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=65536):
                        fh.write(chunk)
            except Exception as exc:
                print(f"  Download failed: {exc}", file=sys.stderr)
                continue

            records.append({
                "video_id": vid_id,
                "source": "pexels",
                "query": query,
                "file_path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
                "expected_content": [w for w in query.split() if len(w) > 3],
                "expected_detections": ["person"],
                "notes": f"Pexels royalty-free stock video — {query}",
            })

    return records


# ---------------------------------------------------------------------------
# Pixabay provider
# ---------------------------------------------------------------------------

def _download_pixabay(queries: list[str], max_per_query: int) -> list[dict]:
    import requests

    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        print("ERROR: PIXABAY_API_KEY not set. Use --provider synthetic instead.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    video_id = len(list(OUTPUT_DIR.glob("*.mp4")))

    for query in queries:
        url = "https://pixabay.com/api/videos/"
        params = {"key": api_key, "q": query, "per_page": max_per_query}
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  Pixabay API error for {query!r}: {exc}", file=sys.stderr)
            continue

        for hit in data.get("hits", [])[:max_per_query]:
            videos_obj = hit.get("videos", {})
            # Prefer small size
            for size_key in ("small", "medium", "large"):
                file_obj = videos_obj.get(size_key)
                if file_obj and file_obj.get("url"):
                    break
            else:
                continue

            dl_url = file_obj["url"]
            video_id += 1
            vid_id = f"test_{video_id:03d}"
            out_path = OUTPUT_DIR / f"{vid_id}.mp4"
            print(f"  Downloading Pixabay video: {out_path.name} ({query!r})")
            try:
                r = requests.get(dl_url, timeout=120, stream=True)
                r.raise_for_status()
                with open(out_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=65536):
                        fh.write(chunk)
            except Exception as exc:
                print(f"  Download failed: {exc}", file=sys.stderr)
                continue

            records.append({
                "video_id": vid_id,
                "source": "pixabay",
                "query": query,
                "file_path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
                "expected_content": [w for w in query.split() if len(w) > 3],
                "expected_detections": ["person"],
                "notes": f"Pixabay royalty-free video — {query}",
            })

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEFAULT_QUERIES = [
    "pedestrians walking street",
    "crowd walking",
    "person running",
    "traffic road",
    "bag backpack scene",
    "general cctv street scene",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=("pexels", "pixabay", "synthetic"), default="synthetic")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES)
    parser.add_argument("--max-per-query", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    global OUTPUT_DIR, MANIFEST_PATH
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

    print(f"Test video provider: {args.provider}")
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Queries: {args.queries}")

    existing: list[dict] = []
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    if args.provider == "synthetic":
        new_records = _generate_synthetic_videos(args.queries, args.max_per_query)
    elif args.provider == "pexels":
        new_records = _download_pexels(args.queries, args.max_per_query)
    else:
        new_records = _download_pixabay(args.queries, args.max_per_query)

    all_records = existing + new_records
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nManifest written: {MANIFEST_PATH}")
    print(f"Total videos: {len(all_records)} ({len(new_records)} new)")
    for r in new_records:
        print(f"  {r['video_id']}: {r['file_path']}")


if __name__ == "__main__":
    main()
