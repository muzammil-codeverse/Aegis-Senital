from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inference.schemas import Detection, FramePacket, Track

logger = logging.getLogger(__name__)

# ── tuning constants ──────────────────────────────────────────────────────────

_WEAPON_CLASSES = frozenset({"weapon", "pistol", "rifle", "knife", "grenade", "gun", "shotgun", "sword"})
_PHONE_CLASSES = frozenset({"phone", "tablet", "cell phone"})

# weapon centroid must be within this pixel distance of a person to count as "in hand"
_WEAPON_PROXIMITY_PX: float = 90.0
# overlap fraction above which a weapon is considered held
_WEAPON_IOU_MIN: float = 0.04
# phone centroid must fall within upper FACE_RATIO of a co-located person bbox
_FACE_REGION_RATIO: float = 0.42
# velocity magnitude (px/frame) below which a track is considered loitering
_LOITERING_SPEED_PX: float = 2.5
# minimum track age (frames) before the loitering label applies
_LOITERING_MIN_AGE: int = 15


# ── geometry helpers ──────────────────────────────────────────────────────────

def _iou(b1: list, b2: list) -> float:
    xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    a1 = max(0.0, b1[2] - b1[0]) * max(0.0, b1[3] - b1[1])
    a2 = max(0.0, b2[2] - b2[0]) * max(0.0, b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0.0 else 0.0


def _center(bbox: list) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _dist(c1: tuple[float, float], c2: tuple[float, float]) -> float:
    return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)


def _speed(velocity: list) -> float:
    """2D speed from velocity vector [dx, dy, ...]."""
    vx = velocity[0] if len(velocity) > 0 else 0.0
    vy = velocity[1] if len(velocity) > 1 else 0.0
    return math.sqrt(vx * vx + vy * vy)


def _best_track(det: "Detection", tracks: list["Track"]) -> "Track | None":
    """Return the active track with the highest IoU overlap with det."""
    best: "Track | None" = None
    best_score = 0.0
    for t in tracks:
        if t.missed_frames > 0:
            continue
        score = _iou(det.bbox, t.bbox)
        if score > best_score:
            best_score = score
            best = t
    return best if best_score > 0.08 else None


# ── main engine ───────────────────────────────────────────────────────────────

class ContextEngine:
    """
    Spatial and temporal context annotator.

    Runs after detection+tracking; enriches each Detection with a ``context``
    dict inside Detection.metadata.  Downstream engines (EventEngine,
    ScenarioEngine) read these labels to reduce false positives and detect
    escalation patterns.

    Annotations produced
    ────────────────────
    weapon_in_hand       bool    weapon bbox is adjacent to / overlaps a person
    weapon_person_iou    float   IoU between weapon and person boxes
    weapon_person_dist   float   centroid distance (px) to nearest person
    phone_near_face      bool    phone centroid is in the face region of a person
    phone_face_ratio     float   relative vertical position inside person bbox
    armed_person         bool    person has a weapon within proximity
    suspicious_loitering bool    track speed < threshold for ≥ LOITERING_MIN_AGE frames
    loiter_speed         float   px/frame
    loiter_age_frames    int     how long the track has been moving slowly
    """

    def annotate(self, packet: "FramePacket") -> int:
        """
        Annotate all detections in *packet* in place.

        Returns the total number of detections that received at least one
        context label (used by SystemMetrics.record_context_annotation).
        """
        detections = packet.detections
        tracks = packet.tracks

        weapon_dets = [d for d in detections if d.class_name in _WEAPON_CLASSES]
        phone_dets = [d for d in detections if d.class_name in _PHONE_CLASSES]
        person_dets = [d for d in detections if d.class_name == "person"]

        annotated = 0
        for det in detections:
            ctx: dict = {}

            if det.class_name in _WEAPON_CLASSES:
                ctx.update(self._weapon_context(det, person_dets))

            if det.class_name in _PHONE_CLASSES:
                ctx.update(self._phone_context(det, person_dets))

            if det.class_name == "person":
                ctx.update(self._person_context(det, weapon_dets))

            ctx.update(self._loitering_context(det, tracks))

            if ctx:
                det.metadata["context"] = ctx
                annotated += 1

        return annotated

    # ── per-class rules ───────────────────────────────────────────────────────

    @staticmethod
    def _weapon_context(
        weapon: "Detection",
        person_dets: list["Detection"],
    ) -> dict:
        w_ctr = _center(weapon.bbox)
        for person in person_dets:
            iou = _iou(weapon.bbox, person.bbox)
            distance = _dist(w_ctr, _center(person.bbox))
            if iou >= _WEAPON_IOU_MIN or distance <= _WEAPON_PROXIMITY_PX:
                return {
                    "weapon_in_hand": True,
                    "weapon_person_iou": round(iou, 3),
                    "weapon_person_dist": round(distance, 1),
                }
        return {}

    @staticmethod
    def _phone_context(
        phone: "Detection",
        person_dets: list["Detection"],
    ) -> dict:
        ph_cx, ph_cy = _center(phone.bbox)
        for person in person_dets:
            px1, py1, px2, py2 = person.bbox
            person_h = max(1.0, py2 - py1)
            face_y_limit = py1 + person_h * _FACE_REGION_RATIO
            h_overlap = px1 <= ph_cx <= px2
            v_in_face = py1 <= ph_cy <= face_y_limit
            if h_overlap and v_in_face:
                return {
                    "phone_near_face": True,
                    "phone_face_ratio": round((ph_cy - py1) / person_h, 3),
                }
        return {}

    @staticmethod
    def _person_context(
        person: "Detection",
        weapon_dets: list["Detection"],
    ) -> dict:
        p_ctr = _center(person.bbox)
        for weapon in weapon_dets:
            if (
                _iou(person.bbox, weapon.bbox) >= _WEAPON_IOU_MIN
                or _dist(p_ctr, _center(weapon.bbox)) <= _WEAPON_PROXIMITY_PX
            ):
                return {"armed_person": True}
        return {}

    @staticmethod
    def _loitering_context(
        det: "Detection",
        tracks: list["Track"],
    ) -> dict:
        track = _best_track(det, tracks)
        if track is None:
            return {}
        speed = _speed(track.velocity)
        age = getattr(track, "age", getattr(track, "last_seen_frame", 0))
        if speed < _LOITERING_SPEED_PX and age >= _LOITERING_MIN_AGE:
            return {
                "suspicious_loitering": True,
                "loiter_speed": round(speed, 3),
                "loiter_age_frames": int(age),
            }
        return {}
