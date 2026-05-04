from __future__ import annotations

import json
import logging
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from inference.camera_graph import CameraGraph
from inference.identity_db import IdentityDB, get_db
from inference.identity_fusion_engine import IdentityFusionEngine
from inference.monitoring.metrics import get_metrics
from inference.schemas import Detection, DetectionResult, FramePacket, Track

logger = logging.getLogger(__name__)

_BBOX_HISTORY_LEN = 8
_VELOCITY_ALPHA = 0.30
_MATCH_THRESHOLD = 0.35
_MAX_AGE_DEFAULT = 30

# BoT-SORT style matching constants
_GATE_MIN_IOU = 0.0               # predicted bbox must have at least this IoU with detection
_APPEARANCE_GATE_THRESHOLD = 0.10 # cosine similarity below this rejects the match
_IDENTITY_DECAY_ON_MISS = 0.90    # confidence multiplied by this each missed frame


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iou(b1: list[float], b2: list[float]) -> float:
    xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0.0 else 0.0


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    lhs = np.asarray(left or [], dtype=np.float32).reshape(-1)
    rhs = np.asarray(right or [], dtype=np.float32).reshape(-1)
    if lhs.size == 0 or rhs.size == 0:
        return 0.0
    dim = max(lhs.size, rhs.size)
    if lhs.size < dim:
        lhs = np.pad(lhs, (0, dim - lhs.size))
    if rhs.size < dim:
        rhs = np.pad(rhs, (0, dim - rhs.size))
    denom = float(np.linalg.norm(lhs) * np.linalg.norm(rhs))
    if denom == 0.0:
        return 0.0
    return float(np.dot(lhs, rhs) / denom)


def _has_embeddings(det: Detection) -> bool:
    return bool(det.face_embedding) and bool(det.appearance_embedding)


@dataclass
class _TrackState:
    track_id: int
    class_name: str
    camera_id: str
    track_uuid: str
    identity_id: str | None = None
    persistent_track_id: str | None = None
    bbox_history: deque[list[float]] = field(default_factory=lambda: deque(maxlen=_BBOX_HISTORY_LEN))
    confidence_history: deque[float] = field(default_factory=lambda: deque(maxlen=_BBOX_HISTORY_LEN))
    velocity: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    face_embedding: list[float] = field(default_factory=list)
    appearance_embedding: list[float] = field(default_factory=list)
    identity_confidence: float = 0.0
    first_seen_frame: int = 0
    last_seen_frame: int = 0
    first_seen_at: str = field(default_factory=_now_iso)
    last_seen_at: str = field(default_factory=_now_iso)
    age: int = 1
    missed_frames: int = 0
    stability_score: float = 0.0
    confidence_trend: float = 0.0
    status: str = "ACTIVE"
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_detection(cls, track_id: int, det: Detection, frame_id: int, camera_id: str) -> _TrackState:
        state = cls(
            track_id=track_id,
            class_name=det.class_name,
            camera_id=camera_id,
            track_uuid=det.metadata.get("track_uuid") or det.detection_id,
            first_seen_frame=frame_id,
            last_seen_frame=frame_id,
            face_embedding=list(det.face_embedding),
            appearance_embedding=list(det.appearance_embedding),
            metadata={"source_model": det.source_model},
        )
        state.bbox_history.append(list(det.bbox))
        state.confidence_history.append(det.confidence)
        state._recompute_stability()
        return state

    @property
    def bbox(self) -> list[float]:
        return list(self.bbox_history[-1]) if self.bbox_history else [0.0, 0.0, 0.0, 0.0]

    @property
    def confidence(self) -> float:
        return float(self.confidence_history[-1]) if self.confidence_history else 0.0

    def predict_bbox(self) -> list[float]:
        bbox = self.bbox
        return [bbox[i] + self.velocity[i] for i in range(4)]

    def absorb(self, det: Detection, frame_id: int, camera_id: str) -> None:
        old_bbox = self.bbox
        self.class_name = det.class_name
        self.camera_id = camera_id
        self.bbox_history.append(list(det.bbox))
        self.confidence_history.append(det.confidence)
        measured_v = [det.bbox[i] - old_bbox[i] for i in range(4)]
        self.velocity = [
            _VELOCITY_ALPHA * measured_v[i] + (1.0 - _VELOCITY_ALPHA) * self.velocity[i]
            for i in range(4)
        ]
        self.face_embedding = list(det.face_embedding)
        self.appearance_embedding = list(det.appearance_embedding)
        self.last_seen_frame = frame_id
        self.last_seen_at = _now_iso()
        self.age += 1
        self.missed_frames = 0
        self.status = "ACTIVE"
        self._recompute_stability()

    def miss(self) -> None:
        self.bbox_history.append(self.predict_bbox())
        self.velocity = [v * (1.0 - _VELOCITY_ALPHA) for v in self.velocity]
        # Decay identity confidence each missed frame so long-absent tracks
        # do not hold stale high-confidence identity assignments.
        self.identity_confidence *= _IDENTITY_DECAY_ON_MISS
        self.age += 1
        self.missed_frames += 1
        self.status = "LOST"
        self._recompute_stability()

    def apply_identity(self, identity_id: str, confidence_score: float) -> None:
        self.identity_id = identity_id
        self.persistent_track_id = identity_id
        self.identity_confidence = confidence_score

    def to_track(self) -> Track:
        return Track(
            track_id=self.track_id,
            class_name=self.class_name,
            bbox=self.bbox,
            confidence=self.confidence,
            last_seen_frame=self.last_seen_frame,
            missed_frames=self.missed_frames,
            velocity=list(self.velocity),
            stability_score=self.stability_score,
            confidence_trend=self.confidence_trend,
            persistent_track_id=self.persistent_track_id,
            track_uuid=self.track_uuid,
            identity_id=self.identity_id,
            camera_id=self.camera_id,
            first_seen_at=self.first_seen_at,
            last_seen_at=self.last_seen_at,
            status=self.status,
            face_embedding=list(self.face_embedding),
            appearance_embedding=list(self.appearance_embedding),
            identity_confidence=self.identity_confidence,
            metadata=dict(self.metadata),
        )

    def _recompute_stability(self) -> None:
        duration = min(1.0, self.age / 30.0)
        detection_rate = max(0.0, 1.0 - self.missed_frames / max(1, self.age))
        age_ramp = min(1.0, self.age / 6.0)
        if len(self.confidence_history) >= 2:
            self.confidence_trend = round(
                (self.confidence_history[-1] - self.confidence_history[0]) / len(self.confidence_history),
                4,
            )
        else:
            self.confidence_trend = 0.0
        smoothness = self._motion_smoothness()
        raw = 0.45 * detection_rate * age_ramp + 0.30 * smoothness + 0.25 * self.confidence
        self.stability_score = round(min(1.0, duration * raw), 4)

    def _motion_smoothness(self) -> float:
        history = list(self.bbox_history)
        if len(history) < 3:
            return 1.0
        speeds = []
        for current, previous in zip(history[1:], history[:-1]):
            dx = ((current[0] + current[2]) / 2.0) - ((previous[0] + previous[2]) / 2.0)
            dy = ((current[1] + current[3]) / 2.0) - ((previous[1] + previous[3]) / 2.0)
            speeds.append(math.sqrt(dx * dx + dy * dy))
        variance = float(np.var(speeds)) if len(speeds) > 1 else 0.0
        return 1.0 / (1.0 + variance / 200.0)


def _motion_similarity(state: _TrackState, det: Detection) -> float:
    predicted = state.predict_bbox()
    pred_cx = (predicted[0] + predicted[2]) / 2.0
    pred_cy = (predicted[1] + predicted[3]) / 2.0
    act_cx = (det.bbox[0] + det.bbox[2]) / 2.0
    act_cy = (det.bbox[1] + det.bbox[3]) / 2.0
    diag = math.sqrt(max(1.0, (det.bbox[2] - det.bbox[0]) ** 2 + (det.bbox[3] - det.bbox[1]) ** 2))
    distance = math.sqrt((pred_cx - act_cx) ** 2 + (pred_cy - act_cy) ** 2)
    return max(0.0, 1.0 - distance / diag)


def _embedding_similarity(state: _TrackState, det: Detection) -> float:
    if not state.appearance_embedding or not det.appearance_embedding:
        return 0.0
    return max(0.0, _cosine_similarity(state.appearance_embedding, det.appearance_embedding))


def _match_score(state: _TrackState, det: Detection) -> float:
    iou = _iou(state.predict_bbox(), det.bbox)
    motion = _motion_similarity(state, det)
    has_emb = bool(state.appearance_embedding) and bool(det.appearance_embedding)

    if not has_emb:
        # Kalman prediction gate: no spatial overlap → reject when no appearance fallback.
        if iou <= _GATE_MIN_IOU:
            return 0.0
        return 0.6 * iou + 0.4 * motion

    emb_sim = _embedding_similarity(state, det)
    # Appearance gate: cosine similarity below threshold rejects the match.
    # This also covers the Kalman gate case (iou=0 AND poor appearance → 0.0).
    if emb_sim < _APPEARANCE_GATE_THRESHOLD:
        return 0.0
    return 0.4 * iou + 0.3 * motion + 0.3 * emb_sim


class MultiObjectTracker:
    """
    Camera-aware tracker with motion prediction and ReID-assisted matching.

    Matching is limited to tracks already active in the current camera, while
    identity continuity across cameras is handled through IdentityFusionEngine.
    """

    def __init__(
        self,
        max_age: int = _MAX_AGE_DEFAULT,
        match_threshold: float = _MATCH_THRESHOLD,
        db: IdentityDB | None = None,
        identity_fusion: IdentityFusionEngine | None = None,
        camera_graph: CameraGraph | None = None,
    ) -> None:
        self.active_tracks: dict[int, _TrackState] = {}
        self.lost_tracks: dict[int, _TrackState] = {}
        self.next_track_id = 1
        self._max_age = max_age
        self._match_threshold = match_threshold
        self._db = db or get_db()
        self._identity_fusion = identity_fusion or IdentityFusionEngine(self._db)
        self._camera_graph = camera_graph

    def update(self, frame_packet: FramePacket) -> list[Track]:
        _t0 = time.monotonic()
        try:
            return self._update_inner(frame_packet)
        finally:
            get_metrics().record_tracking_time(time.monotonic() - _t0)

    def _update_inner(self, frame_packet: FramePacket) -> list[Track]:
        camera_id = frame_packet.camera_id or "default"
        self._identity_fusion.annotate_detections(frame_packet)
        detections = frame_packet.detections
        visible_states = [state for state in self.active_tracks.values() if state.camera_id == camera_id]
        matched_track_to_detection: dict[int, Detection] = {}

        if not detections:
            self._age_camera_tracks(visible_states)
            frame_packet.tracks = self._to_tracks(camera_id)
            return frame_packet.tracks

        if not visible_states:
            for det in detections:
                state = self._spawn(det, frame_packet.frame_id, camera_id)
                matched_track_to_detection[state.track_id] = det
            self._resolve_identities(frame_packet, matched_track_to_detection)
            frame_packet.tracks = self._to_tracks(camera_id)
            return frame_packet.tracks

        score_matrix = [
            [_match_score(state, det) for det in detections]
            for state in visible_states
        ]
        matched_states: set[int] = set()
        matched_detections: set[int] = set()

        while True:
            best_score = 0.0
            best_state_index = -1
            best_detection_index = -1
            for state_index, state in enumerate(visible_states):
                if state.track_id in matched_states:
                    continue
                for detection_index, _ in enumerate(detections):
                    if detection_index in matched_detections:
                        continue
                    score = score_matrix[state_index][detection_index]
                    if score > best_score:
                        best_score = score
                        best_state_index = state_index
                        best_detection_index = detection_index
            if best_score < self._match_threshold:
                break
            state = visible_states[best_state_index]
            detection = detections[best_detection_index]
            state.absorb(detection, frame_packet.frame_id, camera_id)
            matched_states.add(state.track_id)
            matched_detections.add(best_detection_index)
            matched_track_to_detection[state.track_id] = detection

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            state = self._spawn(detection, frame_packet.frame_id, camera_id)
            matched_track_to_detection[state.track_id] = detection

        for state in visible_states:
            if state.track_id in matched_states:
                continue
            state.miss()
            if state.missed_frames > self._max_age:
                state.metadata["predicted_cameras"] = self._predict_camera_handoff(state)
                self.lost_tracks[state.track_id] = self.active_tracks.pop(state.track_id)
                self._db.insert_track(state.to_track())

        self._resolve_identities(frame_packet, matched_track_to_detection)
        logger.debug(
            json.dumps(
                {
                    "event": "tracker_update",
                    "camera_id": camera_id,
                    "frame_id": frame_packet.frame_id,
                    "active_tracks": len([state for state in self.active_tracks.values() if state.camera_id == camera_id]),
                    "detections": len(detections),
                    "ts": _now_iso(),
                }
            )
        )

        frame_packet.tracks = self._to_tracks(camera_id)
        return frame_packet.tracks

    def get_active_tracks(self, camera_id: str | None = None) -> list[Track]:
        return [
            state.to_track()
            for state in self.active_tracks.values()
            if camera_id is None or state.camera_id == camera_id
        ]

    def _resolve_identities(
        self,
        frame_packet: FramePacket,
        matched_track_to_detection: dict[int, Detection],
    ) -> None:
        for track_id, detection in matched_track_to_detection.items():
            state = self.active_tracks.get(track_id)
            if state is None:
                continue
            try:
                track = state.to_track()
                resolution = self._identity_fusion.resolve_track(frame_packet, track, detection=detection)
                state.apply_identity(resolution.identity_id, resolution.confidence_score)
                state.face_embedding = list(resolution.face_embedding)
                state.appearance_embedding = list(resolution.appearance_embedding)
                self._db.insert_track(state.to_track())
            except Exception as exc:
                logger.warning(
                    "Identity resolution failed for track %d — skipping. Error: %s",
                    track_id, exc,
                )

    def _spawn(self, detection: Detection, frame_id: int, camera_id: str) -> _TrackState:
        state = _TrackState.from_detection(self.next_track_id, detection, frame_id, camera_id)
        if not state.track_uuid:
            state.track_uuid = str(uuid.uuid4())
        self.active_tracks[self.next_track_id] = state
        logger.debug(
            json.dumps(
                {
                    "event": "track_created",
                    "track_id": self.next_track_id,
                    "camera_id": camera_id,
                    "class_name": detection.class_name,
                    "frame_id": frame_id,
                    "ts": _now_iso(),
                }
            )
        )
        self.next_track_id += 1
        return state

    def _age_camera_tracks(self, states: list[_TrackState]) -> None:
        for state in states:
            state.miss()
            if state.missed_frames > self._max_age:
                state.metadata["predicted_cameras"] = self._predict_camera_handoff(state)
                self.lost_tracks[state.track_id] = self.active_tracks.pop(state.track_id)
                self._db.insert_track(state.to_track())

    def _predict_camera_handoff(self, state: _TrackState) -> list[dict]:
        if self._camera_graph is None:
            return []
        return self._camera_graph.predict_entry_cameras(
            state.camera_id,
            motion_vector=state.velocity,
            embedding_similarity=state.identity_confidence,
        )

    def _to_tracks(self, camera_id: str) -> list[Track]:
        return [
            state.to_track()
            for state in self.active_tracks.values()
            if state.camera_id == camera_id
        ]


@dataclass
class _LegacyTrack:
    track_id: int
    bbox: list
    missed_frames: int = 0


class ByteTracker:
    """
    Legacy IoU-only tracker that accepts and returns DetectionResult.
    Disabled for production use because degraded tracking is not permitted.
    """

    def __init__(self, max_age: int = 30, iou_threshold: float = 0.3) -> None:
        raise RuntimeError("IoU-only tracker disabled - degraded tracking is not allowed in production mode")
        self._max_age = max_age
        self._iou_threshold = iou_threshold
        self._tracks: list[_LegacyTrack] = []
        self._next_id = 1

    def update(self, result: DetectionResult) -> DetectionResult:
        dets = result.objects
        if not dets:
            for track in self._tracks:
                track.missed_frames += 1
            self._tracks = [track for track in self._tracks if track.missed_frames < self._max_age]
            return result

        if not self._tracks:
            for obj in dets:
                obj.tracking_id = self._next_id
                self._tracks.append(_LegacyTrack(track_id=self._next_id, bbox=obj.bbox))
                self._next_id += 1
            return result

        n_tracks = len(self._tracks)
        n_detections = len(dets)
        iou_matrix = [
            [_iou(self._tracks[track_index].bbox, dets[detection_index].bbox) for detection_index in range(n_detections)]
            for track_index in range(n_tracks)
        ]
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        while True:
            best = 0.0
            best_track = -1
            best_detection = -1
            for track_index in range(n_tracks):
                if track_index in matched_tracks:
                    continue
                for detection_index in range(n_detections):
                    if detection_index in matched_detections:
                        continue
                    if iou_matrix[track_index][detection_index] > best:
                        best = iou_matrix[track_index][detection_index]
                        best_track = track_index
                        best_detection = detection_index
            if best < self._iou_threshold:
                break
            self._tracks[best_track].bbox = dets[best_detection].bbox
            self._tracks[best_track].missed_frames = 0
            dets[best_detection].tracking_id = self._tracks[best_track].track_id
            matched_tracks.add(best_track)
            matched_detections.add(best_detection)

        for detection_index in range(n_detections):
            if detection_index not in matched_detections:
                dets[detection_index].tracking_id = self._next_id
                self._tracks.append(_LegacyTrack(track_id=self._next_id, bbox=dets[detection_index].bbox))
                self._next_id += 1

        for track_index in range(n_tracks):
            if track_index not in matched_tracks:
                self._tracks[track_index].missed_frames += 1
        self._tracks = [track for track in self._tracks if track.missed_frames < self._max_age]
        return result
