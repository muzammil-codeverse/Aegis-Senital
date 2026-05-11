from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.uploaded_video_models import UploadedVideoEvent, UploadedVideoReplayClipMetadata
from app.services import replay_clip_service as rcs
from app.services.replay_clip_service import UploadedVideoReplayClipError, generate_uploaded_video_event_clip_ffmpeg


def test_clip_window_clamps_to_video_bounds(tmp_path, monkeypatch):
    source = tmp_path / "in.mp4"
    source.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x" * 32)
        return MagicMock(returncode=0)

    monkeypatch.setattr(rcs.shutil, "which", lambda _: "/bin/ffmpeg")
    monkeypatch.setattr(rcs.subprocess, "run", fake_run)
    meta = generate_uploaded_video_event_clip_ffmpeg(
        source_video_path=source,
        output_mp4_path=out,
        session_id="uvs_testsession0001",
        event_id="evt_a",
        event_offset_seconds=18.4,
        clip_seconds_before=10.0,
        clip_seconds_after=20.0,
        video_duration_seconds=25.0,
        hash_output=True,
    )
    assert "-ss" in captured["cmd"]
    ss_val = captured["cmd"][captured["cmd"].index("-ss") + 1]
    assert float(ss_val) == pytest.approx(8.4, abs=0.05)
    assert meta["duration_seconds"] == pytest.approx(16.6, abs=0.25)
    assert meta["hash_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


def test_ffmpeg_missing_reports_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(rcs.shutil, "which", lambda _: None)
    source = tmp_path / "in.mp4"
    source.write_bytes(b"x")
    out = tmp_path / "out.mp4"
    with pytest.raises(UploadedVideoReplayClipError, match="ffmpeg"):
        generate_uploaded_video_event_clip_ffmpeg(
            source_video_path=source,
            output_mp4_path=out,
            session_id="uvs_x",
            event_id="evt_x",
            event_offset_seconds=1.0,
            clip_seconds_before=1.0,
            clip_seconds_after=1.0,
            video_duration_seconds=5.0,
            hash_output=True,
        )


def test_ffmpeg_failure_increments_failure_metric(monkeypatch):
    from inference.monitoring.metrics import get_metrics

    tmp = Path(__file__).parent / "_tmp_clip_fail.mp4"
    src = Path(__file__).parent / "_tmp_clip_src.mp4"
    try:
        src.write_bytes(b"src")
        monkeypatch.setattr(rcs.shutil, "which", lambda _: "/bin/ffmpeg")

        def boom(*a, **k):
            raise rcs.subprocess.CalledProcessError(1, cmd=["ffmpeg"], stderr="nope")

        monkeypatch.setattr(rcs.subprocess, "run", boom)
        before = getattr(get_metrics(), "uploaded_video_replay_clip_failures_total", 0)
        with pytest.raises(UploadedVideoReplayClipError):
            generate_uploaded_video_event_clip_ffmpeg(
                source_video_path=src,
                output_mp4_path=tmp,
                session_id="uvs_x",
                event_id="evt_x",
                event_offset_seconds=1.0,
                clip_seconds_before=1.0,
                clip_seconds_after=1.0,
                video_duration_seconds=5.0,
                hash_output=True,
            )
        after = getattr(get_metrics(), "uploaded_video_replay_clip_failures_total", 0)
        assert after >= before + 1
    finally:
        src.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def test_replay_clip_metadata_model_roundtrip():
    m = UploadedVideoReplayClipMetadata(
        clip_id="uvclip_abc",
        session_id="uvs_1",
        event_id="evt_1",
        start_time_seconds=1.0,
        end_time_seconds=3.0,
        duration_seconds=2.0,
        storage_uri="storage/uploaded_video_results/uvs_1/clips/evt_1.mp4",
        hash_sha256="aa" * 32,
        size_bytes=100,
    )
    dumped = m.model_dump(mode="json")
    assert json.loads(json.dumps(dumped))["clip_id"] == "uvclip_abc"


def test_event_optional_replay_clip_field():
    ev = UploadedVideoEvent(
        session_id="uvs_1",
        event_type="anomaly_motion",
        summary="test",
        replay_clip=None,
    )
    assert ev.replay_clip is None
