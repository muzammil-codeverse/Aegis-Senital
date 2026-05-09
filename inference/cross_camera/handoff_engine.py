from __future__ import annotations
from inference.cross_camera.transition_predictor import predict_next
from inference.config_runtime import load_runtime_config

class HandoffEngine:
    def __init__(self) -> None:
        self._graph = load_runtime_config("camera_graph")

    def predict_handoff(self, camera_id: str) -> dict:
        return predict_next(camera_id, self._graph.get("edges", {}))
