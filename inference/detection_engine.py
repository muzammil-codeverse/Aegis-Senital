import numpy as np
from pathlib import Path
from ultralytics import YOLO
from inference.schemas import DetectionResult, DetectedObject

_DEFAULT_MODEL = "yolov8n.pt"


class DetectionEngine:
    """
    YOLO inference wrapper that accepts .pt or .onnx model paths.

    Usage:
        engine = DetectionEngine()                          # default yolov8n.pt
        engine = DetectionEngine("models/exports/weapon_best.onnx")
        engine.load_models()
        result = engine.process_frame(frame, frame_id=0)
    """

    def __init__(self, model_path: str = _DEFAULT_MODEL):
        _ext = Path(model_path).suffix.lower()
        if _ext not in (".pt", ".onnx"):
            raise ValueError(
                f"Unsupported model format '{_ext}'. Must be .pt or .onnx."
            )
        self._model_path = model_path
        self._model: YOLO | None = None

    def load_models(self) -> None:
        self._model = YOLO(self._model_path)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def process_frame(self, frame: np.ndarray, frame_id: int = 0) -> DetectionResult:
        if self._model is None:
            raise RuntimeError("Call load_models() before processing frames.")

        results = self._model(frame, verbose=False)
        objects: list[DetectedObject] = []

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                confidence = round(float(box.conf[0]), 3)
                if confidence <= 0:
                    continue
                x1, y1, x2, y2 = [round(v) for v in box.xyxy[0].tolist()]
                if x2 <= x1 or y2 <= y1:
                    continue
                objects.append(
                    DetectedObject(
                        type=self._model.names[int(box.cls[0])],
                        confidence=confidence,
                        bbox=[x1, y1, x2, y2],
                    )
                )

        return DetectionResult(frame_id=frame_id, objects=objects)
