import os
import cv2
from inference.detection_engine import DetectionEngine
from inference.tracker import ByteTracker
from inference.scenario_engine import get_scenario
from inference.event_buffer import EventBuffer
from app.core.logging_config import logger

FRAME_SKIP = 5
_OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "output")
)

_engine = DetectionEngine()
_engine.load_models()


def extract_frames(video_path: str, scenario: str = "security") -> dict:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    # Fresh instances per video — tracker IDs and buffer state must not bleed across calls
    scenario_obj = get_scenario(scenario)
    tracker = ByteTracker()
    buffer = EventBuffer(window=10, min_consecutive=3)

    logger.info(f"Video processing started: {video_path} | scenario={scenario}")
    frame_index = 0
    frame_results: list[dict] = []
    all_events: list[dict] = []
    confirmed_events: list[dict] = []
    output_frames: list[str] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_index % FRAME_SKIP == 0:
            resized = cv2.resize(frame, (640, 640))

            # 1. YOLO inference
            detection = _engine.process_frame(resized, frame_id=frame_index)

            # 2. Tracking — attach persistent IDs
            detection = tracker.update(detection)

            # 3. Scenario event evaluation
            frame_events = scenario_obj.evaluate(detection)

            # 4. Temporal buffer — confirm only sustained events
            buffer.push(frame_events)
            frame_confirmed = buffer.confirmed_events(frame_events)

            for e in frame_events:
                all_events.append({**e, "frame_id": frame_index})
            for e in frame_confirmed:
                confirmed_events.append({**e, "frame_id": frame_index})

            # 5. Annotate frame with bboxes + tracking IDs
            for obj in detection.objects:
                x1, y1, x2, y2 = obj.bbox
                tid = f"#{obj.tracking_id} " if obj.tracking_id is not None else ""
                cv2.rectangle(resized, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    resized, f"{tid}{obj.type} {obj.confidence:.2f}",
                    (x1, max(y1 - 5, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )

            fname = f"frame_{frame_index:06d}.jpg"
            cv2.imwrite(os.path.join(_OUTPUT_DIR, fname), resized)
            output_frames.append(fname)
            frame_results.append(detection.to_dict())

        frame_index += 1

    cap.release()

    total_detections = sum(len(r["objects"]) for r in frame_results)
    logger.info(
        f"Video processing complete: {frame_index} frames, "
        f"{total_detections} detections, {len(all_events)} raw events, "
        f"{len(confirmed_events)} confirmed"
    )

    return {
        "scenario": scenario,
        "frames": frame_index,
        "frames_sampled": len(frame_results),
        "detections": frame_results,
        "event_summary": {
            "total": len(all_events),
            "confirmed": len(confirmed_events),
            "high": sum(1 for e in confirmed_events if e["severity"] == "high"),
            "medium": sum(1 for e in confirmed_events if e["severity"] == "medium"),
            "low": sum(1 for e in confirmed_events if e.get("severity") == "low"),
            "events": confirmed_events,
        },
        "output_frames": output_frames,
    }
