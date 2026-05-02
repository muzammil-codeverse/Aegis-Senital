import os
import cv2
from inference.detection_engine import DetectionEngine
from app.core.logging_config import logger

FRAME_SKIP = 5
_OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "output")
)

_engine = DetectionEngine()
_engine.load_models()


def extract_frames(video_path: str) -> dict:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    logger.info(f"Video processing started: {video_path}")
    frame_index = 0
    all_detections = []
    output_frames = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % FRAME_SKIP == 0:
            resized = cv2.resize(frame, (640, 640))
            result = _engine.process_frame(resized)

            for obj in result["objects"]:
                x1, y1, x2, y2 = obj["bbox"]
                text = f"{obj['label']} {obj['confidence']:.2f}"
                cv2.rectangle(resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    resized, text, (x1, max(y1 - 5, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )

            fname = f"frame_{frame_index:06d}.jpg"
            cv2.imwrite(os.path.join(_OUTPUT_DIR, fname), resized)
            output_frames.append(fname)
            all_detections.extend(result["objects"])

        frame_index += 1

    cap.release()
    logger.info(
        f"Video processing complete: {frame_index} frames total, "
        f"{len(all_detections)} detections across {len(output_frames)} sampled frames"
    )
    return {
        "frames": frame_index,
        "detections": all_detections,
        "output_frames": output_frames,
    }
