import numpy as np
from ultralytics import YOLO

_yolo_model: YOLO | None = None


def _get_model() -> YOLO:
    global _yolo_model
    if _yolo_model is None:
        _yolo_model = YOLO("yolov8n.pt")
    return _yolo_model


class DetectionEngine:
    def __init__(self):
        self._models_loaded = False

    def load_models(self):
        _get_model()
        self._models_loaded = True

    def process_frame(self, frame: np.ndarray) -> dict:
        if not self._models_loaded:
            raise RuntimeError("Call load_models() before processing frames")

        model = _get_model()
        results = model(frame, verbose=False)

        objects = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                label = model.names[int(box.cls[0])]
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = [round(v) for v in box.xyxy[0].tolist()]
                objects.append({
                    "label": label,
                    "confidence": round(confidence, 3),
                    "bbox": [x1, y1, x2, y2],
                })

        return {"objects": objects}
