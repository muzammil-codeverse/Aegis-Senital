from __future__ import annotations

import math
from typing import Any

from inference.camera_graph import CameraGraph, load_camera_graph_from_config
from inference.config_runtime import load_runtime_config


class HandoffPredictor:
    def __init__(self, config: dict | None = None, camera_graph: CameraGraph | None = None) -> None:
        cfg = config or load_runtime_config("camera_graph")
        self._config = cfg
        self._graph = camera_graph or load_camera_graph_from_config(cfg)
        handoff_cfg = cfg.get("handoff", {})
        self._fps = float(handoff_cfg.get("fps", cfg.get("fps", 30.0)))
        self._meters_per_pixel = float(handoff_cfg.get("meters_per_pixel", 0.05))
        self._default_speed_mps = float(handoff_cfg.get("default_speed_mps", 1.4))
        self._max_predictions = int(handoff_cfg.get("max_predictions", 3))

    def predict(self, camera_id: str, track: Any | None = None, identity_id: str | None = None) -> list[dict]:
        track_id = int(_get(track, "track_id", 0) or 0)
        motion_vector = list(_get(track, "velocity", []) or [])
        identity = identity_id or _get(track, "identity_id")
        predictions: list[dict] = []
        for edge in self._graph.neighbors(camera_id):
            eta = self._estimate_eta(edge.distance_meters, motion_vector)
            if eta < edge.min_travel_seconds:
                continue
            if eta > edge.max_travel_seconds:
                continue
            spatial = edge.overlap_score if edge.overlap_score > 0 else _distance_score(edge.distance_meters)
            motion = self._graph.motion_alignment(motion_vector, edge)
            historical = max(0.0, min(1.0, edge.transition_probability))
            temporal = _temporal_feasibility(eta, edge.min_travel_seconds, edge.max_travel_seconds)
            confidence = 0.35 * spatial + 0.25 * motion + 0.20 * historical + 0.20 * temporal
            predictions.append(
                {
                    "source_camera": camera_id,
                    "candidate_camera": edge.target_camera_id,
                    "identity_id": identity,
                    "track_id": track_id,
                    "eta_seconds": round(float(eta), 3),
                    "confidence": round(max(0.0, min(1.0, confidence)), 4),
                    "route": self._graph.shortest_route(camera_id, edge.target_camera_id) or [camera_id, edge.target_camera_id],
                    "reason": (
                        f"topology={spatial:.2f}, motion={motion:.2f}, "
                        f"history={historical:.2f}, temporal={temporal:.2f}"
                    ),
                }
            )
        predictions.sort(key=lambda item: item["confidence"], reverse=True)
        return predictions[:max(1, self._max_predictions)]

    def predict_best(self, camera_id: str, track: Any | None = None, identity_id: str | None = None) -> dict:
        predictions = self.predict(camera_id, track=track, identity_id=identity_id)
        if predictions:
            return predictions[0]
        return {
            "source_camera": camera_id,
            "candidate_camera": None,
            "identity_id": identity_id or _get(track, "identity_id"),
            "track_id": int(_get(track, "track_id", 0) or 0),
            "eta_seconds": 0.0,
            "confidence": 0.0,
            "route": [],
            "reason": "no allowed feasible camera transition",
        }

    def _estimate_eta(self, distance_meters: float, motion_vector: list[float]) -> float:
        if distance_meters <= 0.0:
            return 0.0
        vx = float(motion_vector[0]) if len(motion_vector) > 0 else 0.0
        vy = float(motion_vector[1]) if len(motion_vector) > 1 else 0.0
        speed_px_per_frame = math.hypot(vx, vy)
        speed_mps = speed_px_per_frame * self._fps * self._meters_per_pixel
        if speed_mps <= 0.05:
            speed_mps = self._default_speed_mps
        return distance_meters / speed_mps


def _temporal_feasibility(eta: float, min_seconds: float, max_seconds: float) -> float:
    if max_seconds <= min_seconds:
        return 1.0
    midpoint = (min_seconds + max_seconds) / 2.0
    half_width = max(1e-6, (max_seconds - min_seconds) / 2.0)
    return round(max(0.0, 1.0 - abs(eta - midpoint) / half_width), 4)


def _distance_score(distance_meters: float) -> float:
    if distance_meters <= 0:
        return 0.5
    return round(1.0 / (1.0 + distance_meters / 100.0), 4)


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
