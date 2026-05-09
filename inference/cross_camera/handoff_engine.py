from __future__ import annotations

from inference.correlation.handoff_predictor import HandoffPredictor

class HandoffEngine:
    def __init__(self) -> None:
        self._predictor = HandoffPredictor()

    def predict_handoff(self, camera_id: str, track: object | None = None, identity_id: str | None = None) -> dict:
        return self._predictor.predict_best(camera_id, track=track, identity_id=identity_id)
