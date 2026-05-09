from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field


@dataclass
class CameraNode:
    camera_id: str
    location_embedding: list[float]
    field_of_view: dict
    metadata: dict = field(default_factory=dict)

    @property
    def location(self) -> list[float]:
        return self.location_embedding


@dataclass
class CameraEdge:
    source_camera_id: str
    target_camera_id: str
    overlap_score: float = 0.0
    transition_probability: float = 0.0
    distance_meters: float = 0.0
    min_travel_seconds: float = 0.0
    max_travel_seconds: float = 300.0
    metadata: dict = field(default_factory=dict)


class CameraGraph:
    """
    Directed camera topology with physical transition constraints.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CameraNode] = {}
        self._edges: dict[str, list[CameraEdge]] = {}

    def add_camera(self, node: CameraNode) -> None:
        self._nodes[node.camera_id] = node
        self._edges.setdefault(node.camera_id, [])

    def connect(self, edge: CameraEdge) -> None:
        if edge.source_camera_id not in self._nodes:
            self.add_camera(CameraNode(edge.source_camera_id, [], {}, {}))
        if edge.target_camera_id not in self._nodes:
            self.add_camera(CameraNode(edge.target_camera_id, [], {}, {}))
        self._edges.setdefault(edge.source_camera_id, []).append(edge)

    def neighbors(self, camera_id: str) -> list[CameraEdge]:
        return list(self._edges.get(camera_id, []))

    def get_edge(self, source_camera_id: str, target_camera_id: str) -> CameraEdge | None:
        return next(
            (
                edge for edge in self._edges.get(source_camera_id, [])
                if edge.target_camera_id == target_camera_id
            ),
            None,
        )

    def transition_allowed(self, source_camera_id: str, target_camera_id: str) -> bool:
        return self.get_edge(source_camera_id, target_camera_id) is not None

    def shortest_route(self, source_camera_id: str, target_camera_id: str) -> list[str]:
        if source_camera_id == target_camera_id:
            return [source_camera_id]
        queue: list[tuple[float, str, list[str]]] = [(0.0, source_camera_id, [source_camera_id])]
        seen: set[str] = set()
        while queue:
            cost, camera_id, route = heapq.heappop(queue)
            if camera_id in seen:
                continue
            seen.add(camera_id)
            for edge in self.neighbors(camera_id):
                if edge.target_camera_id in seen:
                    continue
                next_route = route + [edge.target_camera_id]
                if edge.target_camera_id == target_camera_id:
                    return next_route
                edge_cost = edge.distance_meters if edge.distance_meters > 0 else 1.0
                heapq.heappush(queue, (cost + edge_cost, edge.target_camera_id, next_route))
        return []

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
                    "distance_meters": edge.distance_meters,
                    "min_travel_seconds": edge.min_travel_seconds,
                    "max_travel_seconds": edge.max_travel_seconds,
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
        edge = self.get_edge(source_camera_id, target_camera_id)
        if edge is None:
            return 0.0
        spatial = edge.overlap_score if edge.overlap_score > 0.0 else _distance_score(edge.distance_meters)
        motion_score = self.motion_alignment(motion_vector, edge)
        historical = max(0.0, min(1.0, edge.transition_probability))
        identity = max(0.0, min(1.0, embedding_similarity))
        score = 0.35 * spatial + 0.25 * motion_score + 0.25 * historical + 0.15 * identity
        return round(min(1.0, max(0.0, score)), 4)

    def motion_alignment(self, motion_vector: list[float] | None, edge: CameraEdge) -> float:
        return self._motion_alignment(motion_vector, edge.metadata)

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
        delta = abs(((observed_heading - float(expected_heading) + 180.0) % 360.0) - 180.0)
        return round(max(0.0, 1.0 - delta / 180.0), 4)


def load_camera_graph_from_config(config: dict) -> CameraGraph:
    graph = CameraGraph()

    for cam_id, cam_cfg in config.get("cameras", {}).items():
        location = cam_cfg.get("location", [])
        fov = cam_cfg.get("fov", {})
        if "fov_degrees" in cam_cfg:
            fov = {**dict(fov), "degrees": cam_cfg.get("fov_degrees")}
        node = CameraNode(
            camera_id=cam_id,
            location_embedding=[float(v) for v in location],
            field_of_view=dict(fov),
            metadata={k: v for k, v in cam_cfg.items() if k not in ("location", "fov", "fov_degrees")},
        )
        graph.add_camera(node)

    for source, targets in config.get("edges", {}).items():
        for target, meta in (targets or {}).items():
            graph.connect(
                CameraEdge(
                    source_camera_id=source,
                    target_camera_id=target,
                    overlap_score=float(meta.get("overlap", meta.get("weight", 0.0))),
                    transition_probability=float(meta.get("probability", meta.get("weight", 0.0))),
                    distance_meters=float(meta.get("distance_meters", 0.0)),
                    min_travel_seconds=float(meta.get("min_travel_seconds", 0.0)),
                    max_travel_seconds=float(meta.get("max_travel_seconds", meta.get("eta_seconds", 300.0))),
                    metadata={"heading": meta["heading"]} if "heading" in meta else {},
                )
            )

    for conn in config.get("connections", []):
        source = conn.get("from", "")
        target = conn.get("to", "")
        if not source or not target:
            continue
        graph.connect(
            CameraEdge(
                source_camera_id=source,
                target_camera_id=target,
                overlap_score=float(conn.get("overlap", conn.get("overlap_score", 0.0))),
                transition_probability=float(conn.get("transition_probability", conn.get("probability", 0.0))),
                distance_meters=float(conn.get("distance_meters", 0.0)),
                min_travel_seconds=float(conn.get("min_travel_seconds", 0.0)),
                max_travel_seconds=float(conn.get("max_travel_seconds", 300.0)),
                metadata={k: v for k, v in conn.items() if k not in {
                    "from",
                    "to",
                    "overlap",
                    "overlap_score",
                    "probability",
                    "transition_probability",
                    "distance_meters",
                    "min_travel_seconds",
                    "max_travel_seconds",
                }},
            )
        )

    return graph


def _distance_score(distance_meters: float) -> float:
    if distance_meters <= 0.0:
        return 0.5
    return round(1.0 / (1.0 + distance_meters / 100.0), 4)
