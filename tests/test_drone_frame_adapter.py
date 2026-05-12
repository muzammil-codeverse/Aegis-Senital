import base64

import cv2
import numpy as np

from app.models.drone_simulation_models import DroneCameraFrame, DroneTelemetry
from inference.drone.drone_frame_adapter import DroneFrameAdapter


def test_drone_frame_adapter_produces_decoded_packet_metadata():
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[:, :] = (0, 127, 255)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok is True

    telemetry = DroneTelemetry(
        status="connected",
        latitude=30.1575,
        longitude=71.5249,
        altitude_meters=40.0,
    )
    frame = DroneCameraFrame(
        status="connected",
        frame_available=True,
        frame_index=123,
        width=8,
        height=8,
        image_base64=base64.b64encode(encoded.tobytes()).decode("ascii"),
        telemetry=telemetry,
    )

    packet = DroneFrameAdapter.to_decoded_packet(frame, telemetry)

    assert packet.camera_id == "drone_sim_01"
    assert packet.frame_index == 123
    assert packet.frame.shape[0] == 8
    assert packet.metadata["source_type"] == "drone_simulation"
    assert packet.metadata["simulated"] is True
    assert packet.metadata["drone_id"] == "drone_sim_01"
    assert packet.metadata["telemetry"]["latitude"] == 30.1575
