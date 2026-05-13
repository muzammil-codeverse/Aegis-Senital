#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "datasets" / "demo_videos"
MANIFEST_PATH = TARGET_DIR / "manifest.json"

TARGETS = {
    "demo_crowd_street.mp4": [
        "https://samplelib.com/lib/preview/mp4/sample-5s.mp4",
    ],
    "demo_traffic_road.mp4": [
        "https://samplelib.com/lib/preview/mp4/sample-10s.mp4",
    ],
    "demo_people_walking.mp4": [
        "https://samplelib.com/lib/preview/mp4/sample-15s.mp4",
    ],
    "demo_general_cctv.mp4": [
        "https://samplelib.com/lib/preview/mp4/sample-20s.mp4",
    ],
}

FALLBACKS = [
    "datasets/test_videos/test_001.mp4",
    "datasets/test_videos/test_002.mp4",
    "datasets/test_videos/test_003.mp4",
    "datasets/test_videos/test_004.mp4",
]


def _download(url: str, destination: Path, timeout: int) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        return destination.exists() and destination.stat().st_size > 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local demo video manifest with online-first and fallback entries.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--max-videos", type=int, default=4)
    parser.add_argument("--prefer-small", action="store_true")
    args = parser.parse_args()

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    selected_targets = list(TARGETS.items())[: max(1, min(args.max_videos, len(TARGETS)))]
    for index, (filename, urls) in enumerate(selected_targets):
        target_path = TARGET_DIR / filename
        downloaded = False
        selected_url = None
        candidate_urls = list(urls)
        if args.prefer_small:
            candidate_urls = sorted(candidate_urls, key=len)
        if not args.skip_download:
            for url in candidate_urls:
                if _download(url, target_path, args.timeout):
                    downloaded = True
                    selected_url = url
                    break
        if downloaded:
            items.append(
                {
                    "name": filename,
                    "path": str(target_path.relative_to(ROOT)).replace("\\", "/"),
                    "downloaded": True,
                    "source_url": selected_url,
                    "simulated": True,
                    "demo": True,
                    "operator_review_required": True,
                }
            )
        else:
            fallback = FALLBACKS[min(index, len(FALLBACKS) - 1)]
            items.append(
                {
                    "name": filename,
                    "path": fallback,
                    "downloaded": False,
                    "source_url": None,
                    "simulated": True,
                    "demo": True,
                    "operator_review_required": True,
                    "fallback": True,
                }
            )

    manifest = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "items": items,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "manifest": str(MANIFEST_PATH.resolve()), "count": len(items)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
