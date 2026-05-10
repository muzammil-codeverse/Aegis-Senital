import time
import pytest
from inference.anomaly.temporal_buffer import TemporalBuffer


def _make_track(tid):
    return {"track_id": tid, "class_name": "person", "confidence": 0.85, "bbox": [10, 10, 50, 80]}


def test_add_frame_creates_camera_window():
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=1)
    buf.add_frame("cam1", 1, time.time(), [], [], None)
    assert "cam1" in buf.active_cameras()


def test_get_window_returns_anomaly_window():
    from inference.anomaly.schemas import AnomalyWindow
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=1)
    buf.add_frame("cam1", 1, time.time(), [], [_make_track(1)], None)
    win = buf.get_window("cam1")
    assert isinstance(win, AnomalyWindow)
    assert win.camera_id == "cam1"


def test_rolling_window_per_camera():
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=1)
    buf.add_frame("cam_a", 1, time.time(), [], [], None)
    buf.add_frame("cam_b", 1, time.time(), [], [], None)
    cams = buf.active_cameras()
    assert "cam_a" in cams
    assert "cam_b" in cams


def test_buffer_eviction():
    buf = TemporalBuffer(window_seconds=0.1, sample_rate=1)
    now = time.time()
    buf.add_frame("cam1", 1, now - 10, [], [], None)  # old frame
    buf.add_frame("cam1", 2, now, [], [], None)        # triggers eviction
    win = buf.get_window("cam1")
    # Old frame should be evicted
    for f in win.frames:
        assert f.get("timestamp", now) >= now - 0.5


def test_clear_camera():
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=1)
    buf.add_frame("cam1", 1, time.time(), [], [_make_track(1)], None)
    buf.clear_camera("cam1")
    win = buf.get_window("cam1")
    assert win is None or len(win.frames) == 0


def test_sample_rate_filtering():
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=3)
    now = time.time()
    for i in range(9):
        buf.add_frame("cam1", i, now + i, [], [], None)
    win = buf.get_window("cam1")
    # Only every 3rd frame stored (3 of 9)
    assert len(win.frames) == 3


def test_missing_camera_returns_none():
    buf = TemporalBuffer()
    assert buf.get_window("does_not_exist") is None


def test_buffer_sizes():
    buf = TemporalBuffer(window_seconds=5.0, sample_rate=1)
    buf.add_frame("cam1", 1, time.time(), [], [], None)
    buf.add_frame("cam1", 2, time.time(), [], [], None)
    sizes = buf.buffer_sizes()
    assert "cam1" in sizes
    assert sizes["cam1"] >= 1
