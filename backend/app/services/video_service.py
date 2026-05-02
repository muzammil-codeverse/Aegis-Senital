import cv2
from inference.detection_engine import DetectionEngine
from app.core.logging_config import logger

_engine = DetectionEngine()
_engine.load_models()


def extract_frames(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    logger.info(f"Video processing started: {video_path}")
    frame_count = 0
    detections = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        detections.append(_engine.process_frame(frame))

    cap.release()
    logger.info(f"Video processing complete: {frame_count} frames processed")
    return {"frames": frame_count, "detections": detections}
