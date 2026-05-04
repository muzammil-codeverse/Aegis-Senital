from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class CameraNode:
    camera_id: str
    location_embedding: list[float]
    field_of_view: dict
    metadata: dict = field(default_factory=dict)


@dataclass
class CameraEdge:
    source_camera_id: str
    target_camera_id: str
    overlap_score: float
    transition_probability: float
    metadata: dict = field(default_factory=dict)


class CameraGraph:
    """
    Directed camera connectivity graph for cross-camera track propagation.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CameraNode] = {}
        self._edges: dict[str, list[CameraEdge]] = {}

    def add_camera(self, node: CameraNode) -> None:
        self._nodes[node.camera_id] = node
        self._edges.setdefault(node.camera_id, [])

    def connect(self, edge: CameraEdge) -> None:
        self._edges.setdefault(edge.source_camera_id, []).append(edge)

    def neighbors(self, camera_id: str) -> list[CameraEdge]:
        return list(self._edges.get(camera_id, []))

    def predict_entry_cameras(
        self,
        source_camera_id: str,
        *,
        motion_vector: list[float] | None = None,
        embedding_similarity: float = 0.0,
        top_k: int = 3,
    ) -> list[dict]:
        scored = []
        for edge in self.neighbors(source_camera_id):
            score = self.score_transition(
                edge.source_camera_id,
                edge.target_camera_id,
                motion_vector=motion_vector,
                embedding_similarity=embedding_similarity,
            )
            scored.append(
                {
                    "camera_id": edge.target_camera_id,
                    "score": score,
                    "overlap_score": edge.overlap_score,
                    "transition_probability": edge.transition_probability,
                }
            )
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:max(1, top_k)]

    def score_transition(
        self,
        source_camera_id: str,
        target_camera_id: str,
        *,
        motion_vector: list[float] | None = None,
        embedding_similarity: float = 0.0,
    ) -> float:
        edge = next(
            (item for item in self._edges.get(source_camera_id, []) if item.target_camera_id == target_camera_id),
            None,
        )
        if edge is None:
            return 0.0
        motion_score = self._motion_alignment(motion_vector, edge.metadata)
        score = (
            0.45 * edge.transition_probability
            + 0.25 * edge.overlap_score
            + 0.15 * motion_score
            + 0.15 * max(0.0, min(1.0, embedding_similarity))
        )
        return round(min(1.0, max(0.0, score)), 4)

    @staticmethod
    def _motion_alignment(motion_vector: list[float] | None, metadata: dict) -> float:
        if not motion_vector:
            return 0.5
        expected_heading = metadata.get("heading")
        if expected_heading is None:
            return 0.5
        vx = float(motion_vector[0]) if len(motion_vector) > 0 else 0.0
        vy = float(motion_vector[1]) if len(motion_vector) > 1 else 0.0
        if vx == 0.0 and vy == 0.0:
            return 0.5
        observed_heading = math.degrees(math.atan2(vy, vx))
        delta = abs(((observed_heading - expected_heading + 180.0) % 360.0) - 180.0)
        return round(max(0.0, 1.0 - delta / 180.0), 4)
