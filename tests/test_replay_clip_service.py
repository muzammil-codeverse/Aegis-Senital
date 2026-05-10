from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from app.services.replay_clip_service import ReplayClipService


def _write_video(path, frames=20, fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (32, 24))
    for _ in range(frames):
        writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
    writer.release()


def test_replay_clip_service_exports_file_backed_clip(tmp_path, monkeypatch):
    video_path = tmp_path / "source.mp4"
    _write_video(video_path)
    base_ts = datetime.now(timezone.utc)

    class _FakeProcessor:
        source = str(video_path)
        source_type = "file"

    session_manager = type("Manager", (), {
        "get_stream_stats": lambda self, _camera_id: {
            "source_base_timestamp": base_ts.isoformat(),
            "last_source_timestamp": (base_ts + timedelta(seconds=1)).isoformat(),
            "last_frame_at": (base_ts + timedelta(seconds=1)).isoformat(),
        },
        "get_stream_processor": lambda self, _camera_id: _FakeProcessor(),
    })()

    monkeypatch.setattr("app.services.replay_clip_service.get_stream_session_manager", lambda: session_manager)
    service = ReplayClipService()
    response = service.export_clip("cam_01", {
        "start_at": (base_ts + timedelta(seconds=0.2)).isoformat(),
        "end_at": (base_ts + timedelta(seconds=1.2)).isoformat(),
    })

    assert response.status == "ready"
    assert response.file_path is not None

