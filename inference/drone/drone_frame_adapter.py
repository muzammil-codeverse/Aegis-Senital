from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np

from app.models.drone_simulation_models import DroneCameraFrame, DroneTelemetry
from app.services.rtsp_ingest_service import DecodedFramePacket


class DroneFrameAdapter:
    @staticmethod
    def decode_frame_array(frame: DroneCameraFrame) -> np.ndarray:
        if not frame.image_base64:
            raise ValueError("No simulated drone frame is available")
        binary = base64.b64decode(frame.image_base64.encode("ascii"))
        array = np.frombuffer(binary, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode simulated drone frame")
        return image

    @staticmethod
    def metadata(frame: DroneCameraFrame, telemetry: DroneTelemetry | None = None) -> dict[str, Any]:
        return {
            "source_type": "drone_simulation",
            "camera_id": frame.drone_id,
            "drone_id": frame.drone_id,
            "simulated": True,
            "telemetry": telemetry.model_dump(mode="json") if telemetry is not None else {},
            "frame_index": frame.frame_index,
            "timestamp": frame.timestamp,
        }

    @classmethod
    def to_decoded_packet(
        cls,
        frame: DroneCameraFrame,
        telemetry: DroneTelemetry | None = None,
    ) -> DecodedFramePacket:
        image = cls.decode_frame_array(frame)
        return DecodedFramePacket(
            camera_id=frame.drone_id,
            frame=image,
            frame_index=frame.frame_index,
            timestamp=frame.timestamp,
            source_timestamp=frame.timestamp,
            width=int(frame.width or image.shape[1]),
            height=int(frame.height or image.shape[0]),
            fps_estimate=0.0,
            metadata=cls.metadata(frame, telemetry or frame.telemetry),
        )
