#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = ROOT / "backend"
for candidate in (ROOT, BACKEND_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.services.rtsp_ingest_service import RTSPIngestService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate a streaming source from a local video file.")
    parser.add_argument("--video", required=True, help="Path to the local video file.")
    parser.add_argument("--camera-id", required=True, help="Camera identifier for the simulated source.")
    parser.add_argument("--loop", action="store_true", help="Loop the input video indefinitely.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after this many frames (0 = unlimited).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_path = Path(args.video).resolve()
    if not video_path.exists():
        raise SystemExit(f"video not found: {video_path}")

    stop_event = threading.Event()
    frames_seen = 0

    print(f"Simulating file-backed stream for camera '{args.camera_id}' from {video_path}")
    while not stop_event.is_set():
        ingest = RTSPIngestService(
            camera_id=args.camera_id,
            source=str(video_path),
            source_type="file",
        )
        print(f"source_type={ingest.source_type} loop={args.loop}")
        while not stop_event.is_set():
            packet = ingest.read_packet(stop_event)
            if packet is None:
                break
            frames_seen += 1
            if frames_seen == 1 or frames_seen % 30 == 0:
                print(
                    f"frame={packet.frame_index} ts={packet.timestamp} "
                    f"source_ts={packet.source_timestamp} fps={packet.fps_estimate:.2f}"
                )
            if args.max_frames and frames_seen >= args.max_frames:
                stop_event.set()
                break
        ingest.close()
        if not args.loop:
            break
        time.sleep(0.1)

    print(f"simulation complete frames_seen={frames_seen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
