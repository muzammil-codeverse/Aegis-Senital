import numpy as np


class DetectionEngine:
    def __init__(self):
        self._models_loaded = False

    def load_models(self):
        # Placeholder — swap in real model loading (YOLO, DeepFace, etc.)
        self._models_loaded = True

    def process_frame(self, frame: np.ndarray) -> dict:
        if not self._models_loaded:
            raise RuntimeError("Call load_models() before processing frames")

        # Mock response — replace with actual inference
        return {
            "objects": [],
            "faces": [],
        }
