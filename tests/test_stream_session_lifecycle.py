from backend.app.services.stream_session_manager import StreamSessionManager


class _FakeStreamManager:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_stream(self, source: str, stream_id: str | None = None) -> str:
        self.added.append((source, stream_id))
        return stream_id or "stream_0"

    def remove_stream(self, stream_id: str) -> bool:
        self.removed.append(stream_id)
        return True


def test_stream_session_start_stop_restart(monkeypatch):
    fake_manager = _FakeStreamManager()
    manager = StreamSessionManager()
    monkeypatch.setattr(manager, "_get_camera_source", lambda _camera_id: "rtsp://demo")
    monkeypatch.setattr(manager, "_prepare_open_vocab_for_stream", lambda _camera_id: {"status": "ok", "block_stream": False})
    monkeypatch.setattr("inference.stream.stream_manager.get_stream_manager", lambda: fake_manager)

    started = manager.start_stream("cam_01")
    restarted = manager.restart_stream("cam_01")
    stopped = manager.stop_stream("cam_01")

    assert started["state"] == "running"
    assert restarted["state"] == "running"
    assert stopped["state"] == "stopped"
    assert fake_manager.added[0][1] == "cam_cam_01"
    assert "cam_cam_01" in fake_manager.removed

