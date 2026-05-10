import threading

import numpy as np

from app.services.rtsp_ingest_service import RTSPIngestService


class _FakeCapture:
    def __init__(self, frame):
        self._frame = frame
        self._reads = 0

    def isOpened(self):
        return True

    def set(self, *_args, **_kwargs):
        return True

    def read(self):
        self._reads += 1
        if self._reads > 1:
            return False, None
        return True, self._frame.copy()

    def release(self):
        return None

    def get(self, prop):
        return 1000.0 if prop else 0.0


def test_rtsp_ingest_service_reads_packet(monkeypatch):
    frame = np.zeros((32, 48, 3), dtype=np.uint8)
    monkeypatch.setattr("app.services.rtsp_ingest_service.cv2.VideoCapture", lambda *_args, **_kwargs: _FakeCapture(frame))
    service = RTSPIngestService(camera_id="cam_01", source="demo.mp4", source_type="file")

    packet = service.read_packet(threading.Event())

    assert packet is not None
    assert packet.camera_id == "cam_01"
    assert packet.width == 48
    assert packet.height == 32
    snapshot = service.snapshot()
    assert snapshot["frames_decoded_total"] == 1
    assert snapshot["last_source_timestamp"] is not None

