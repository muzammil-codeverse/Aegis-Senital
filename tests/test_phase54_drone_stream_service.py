from app.models.drone_simulation_models import DroneRuntimeStatus
from app.services.drone.drone_stream_service import DroneStreamService


class _FakeService:
    def __init__(self):
        self.drone_id = "drone_sim_01"
        self.allowed_cameras = ("front_center", "downward")
        self.config = {
            "drone_stream": {
                "enabled": True,
                "default_fps": 5,
                "max_fps": 10,
                "cameras": ["front_center", "downward"],
                "process_all_cameras": False,
                "preview_all_cameras": True,
                "inference_cameras": ["front_center"],
            }
        }

    def get_multi_camera_frames(self, camera_names):
        del camera_names
        return []

    def get_runtime_status(self):
        return DroneRuntimeStatus(selected_runtime="AirSimNH", connected=False)


def test_phase54_drone_stream_service_disabled_returns_empty():
    service = _FakeService()
    stream = DroneStreamService(service, config={"enabled": False})
    stream.start()
    assert stream.capture_and_process() == []


def test_phase54_drone_stream_service_preview_camera_selection():
    service = _FakeService()
    stream = DroneStreamService(service, config=service.config["drone_stream"])
    stream.start()
    frames = stream.capture_and_process()
    assert frames == []
    stats = stream.stats()
    assert stats["frames_captured_total"] == 0
