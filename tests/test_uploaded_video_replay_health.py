from __future__ import annotations

from pathlib import Path

from app.services.uploaded_video_service import UploadedVideoService
from uploaded_video_test_utils import uploaded_video_config


def test_uploaded_video_health_includes_replay_block(tmp_path):
    cfg = uploaded_video_config(tmp_path)
    cfg["uploaded_video"]["replay"]["enabled"] = True
    service = UploadedVideoService(config=cfg)
    health = service.health()
    assert "replay_enabled" in health
    assert "ffmpeg_available" in health
    assert "clip_generation_status" in health
