from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from starlette.datastructures import Headers, UploadFile


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.services.uploaded_video_service import get_uploaded_video_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the uploaded-video workflow end-to-end.")
    parser.add_argument("--video", required=True, help="Path to the input video file")
    parser.add_argument("--device", default="cuda", help="Requested processing device hint")
    parser.add_argument("--max-frames", type=int, default=120, help="Maximum frames to process")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 2

    service = get_uploaded_video_service()
    with video_path.open("rb") as handle:
        upload = UploadFile(
            file=handle,
            filename=video_path.name,
            headers=Headers({"content-type": "video/mp4"}),
        )
        response = service.upload_video(
            upload,
            {"max_frames": args.max_frames, "metadata": {"requested_device": args.device}},
            "smoke-test",
        )
    session_id = response.session.session_id
    print(f"Uploaded session: {session_id}")
    service.start_processing(session_id, "smoke-test")

    deadline = time.time() + 600
    while time.time() < deadline:
        status = service.get_status(session_id)
        print(f"status={status.status} progress={status.progress.percent:.1f}% events={status.event_count}")
        if status.status in {"completed", "failed", "cancelled"} and not status.active:
            report = service.get_report(session_id)
            print(f"final_status={status.status} report_ready={bool(report)}")
            return 0 if status.status == "completed" else 1
        time.sleep(2.0)

    print("Timed out waiting for uploaded-video workflow to finish")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
