from inference.stream.stream_session_manager import StreamRuntimeSessionManager


class _FakeProcessor:
    def __init__(self, stream_id: str, camera_id: str, status: str):
        self.stream_id = stream_id
        self.camera_id = camera_id
        self._status = status

    @property
    def is_running(self) -> bool:
        return self._status != "stopped"

    def get_status(self) -> dict:
        return {"stream_id": self.stream_id, "camera_id": self.camera_id}

    def get_stream_health(self) -> dict:
        return {"camera_id": self.camera_id, "status": self._status, "last_error": None}

    def get_stream_stats(self) -> dict:
        return {"camera_id": self.camera_id, "fps_decode": 10.0}

    def get_preview_frame_jpeg(self):
        return None, None


def test_runtime_stream_health_summary():
    manager = StreamRuntimeSessionManager()
    manager.register(_FakeProcessor("stream_1", "cam_01", "healthy"))
    manager.register(_FakeProcessor("stream_2", "cam_02", "degraded"))

    summary = manager.health_summary()

    assert summary["streaming"]["active_streams"] == 2
    assert summary["streaming"]["degraded_streams"] == 1
    assert summary["streaming"]["status"] in {"degraded", "healthy"}

