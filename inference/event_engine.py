from __future__ import annotations

import json
import logging
import math
from collections import deque
from datetime import datetime, timezone

from inference.event_buffer import EventBuffer
from inference.identity_db import IdentityDB, get_db
from inference.monitoring.metrics import get_metrics
from inference.schemas import DetectionResult, Event, FramePacket, Track

logger = logging.getLogger(__name__)

_CLASS_WEIGHTS: dict[str, float] = {
    "weapon": 0.95,
    "pistol": 0.95,
    "rifle": 0.95,
    "knife": 0.85,
    "grenade": 0.98,
    "gun": 0.95,
    "shotgun": 0.95,
    "sword": 0.80,
    "phone": 0.45,
    "tablet": 0.40,
    "cell phone": 0.45,
    "person": 0.15,
}
_DEFAULT_CLASS_WEIGHT = 0.25

WEAPON_LABELS = frozenset({"weapon", "pistol", "rifle", "knife", "grenade", "gun", "shotgun", "sword"})
PHONE_LABELS = frozenset({"phone", "tablet", "cell phone"})

_BASE_THRESHOLD = 0.30
_WEAPON_THRESHOLD = 0.40
_PHONE_THRESHOLD = 0.36
_DECAY_LAMBDA = 0.35
_WEAPON_CONFIRMATION = 3
_PHONE_CONFIRMATION = 2


def _parse_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.now(timezone.utc)


def _severity(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


def _iou(b1: list[float], b2: list[float]) -> float:
    xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


class EventEngine:
    """
    Temporal threat scoring engine with decayed memory and queued persistence.
    """

    def __init__(self, db: IdentityDB | None = None) -> None:
        self._db = db or get_db()
        self._score_memory: dict[str, tuple[float, datetime]] = {}
        # Phase 5 — adaptive threshold state
        # Sliding window of risk scores from recently emitted events.
        # Low-scoring events (near threshold) are treated as noise signals.
        self._recent_event_scores: deque[float] = deque(maxlen=30)
        # Rolling avg detections per frame (feeds stream_load_factor)
        self._recent_det_counts: deque[int] = deque(maxlen=20)

    def evaluate(self, buffer: EventBuffer) -> list[Event]:
        if len(buffer) == 0:
            return []
        recent = buffer.get_recent(1)
        if not recent:
            return []
        packet = recent[-1]

        # Track rolling detection count before computing threshold
        self._recent_det_counts.append(len(packet.detections))
        threshold = self._adaptive_threshold(buffer.get_scene_density(), len(packet.tracks))
        tracks = [track for track in packet.tracks if track.missed_frames == 0]

        events: list[Event] = []
        events.extend(self._weapon_events(packet, tracks, buffer, threshold))
        events.extend(self._phone_events(packet, tracks, buffer, threshold))
        events.extend(self._crowd_events(packet, tracks, events))

        for event in events:
            self._db.persist_event(event, frame_id=packet.frame_id)
            self._recent_event_scores.append(event.risk_score)

        if events:
            _m = get_metrics()
            _m.increment("events_generated", len(events))
            high_count = sum(
                1 for e in events if e.priority_level in ("HIGH", "CRITICAL")
            )
            if high_count:
                _m.record_high_priority_event(high_count)
            logger.info(
                json.dumps(
                    {
                        "event": "events_fired",
                        "frame_id": packet.frame_id,
                        "camera_id": packet.camera_id,
                        "count": len(events),
                        "types": [event.event_type for event in events],
                        "priorities": [event.priority_level for event in events],
                        "threshold": threshold,
                        "ts": packet.timestamp,
                    }
                )
            )
        return events

    def _weapon_events(
        self,
        packet: FramePacket,
        tracks: list[Track],
        buffer: EventBuffer,
        threshold: float,
    ) -> list[Event]:
        events: list[Event] = []
        for track in tracks:
            if track.class_name not in WEAPON_LABELS:
                continue
            series = buffer.get_track_series(track.track_id)
            if series is None or series.duration_frames < _WEAPON_CONFIRMATION:
                continue
            score, components = self._score_track(packet, track, track.class_name)
            if series.threat_score_series:
                series.threat_score_series[-1] = score
            if score < max(threshold, _WEAPON_THRESHOLD):
                continue
            events.append(self._build_event(packet, track, score, "WEAPON_THREAT", components))
        return events

    def _phone_events(
        self,
        packet: FramePacket,
        tracks: list[Track],
        buffer: EventBuffer,
        threshold: float,
    ) -> list[Event]:
        events: list[Event] = []
        phone_tracks = [track for track in tracks if track.class_name in PHONE_LABELS]
        person_tracks = [track for track in tracks if track.class_name == "person"]
        for track in phone_tracks:
            series = buffer.get_track_series(track.track_id)
            if series is None or series.duration_frames < _PHONE_CONFIRMATION:
                continue
            base_score, components = self._score_track(packet, track, "phone")
            if series.threat_score_series:
                series.threat_score_series[-1] = base_score
            proximity = max((_iou(track.bbox, person.bbox) for person in person_tracks), default=0.0)
            final_score = min(1.0, base_score + 0.20 * proximity)
            if final_score < min(max(0.24, threshold - 0.05), _PHONE_THRESHOLD):
                continue
            components["proximity"] = round(proximity, 4)
            events.append(self._build_event(packet, track, final_score, "PHONE_USAGE_RISK", components))
        return events

    def _crowd_events(self, packet: FramePacket, tracks: list[Track], events: list[Event]) -> list[Event]:
        people = [track for track in tracks if track.class_name == "person"]
        weapons = [event for event in events if event.event_type == "WEAPON_THREAT"]
        if len(people) < 3 or not weapons:
            return []
        mean_weapon_score = sum(event.risk_score for event in weapons) / len(weapons)
        crowd_factor = min(1.0, len(people) / 6.0)
        final_score = min(1.0, 0.70 * mean_weapon_score + 0.30 * crowd_factor)
        primary = max(weapons, key=lambda event: event.risk_score)
        event = Event(
            event_type="ARMED_CROWD_THREAT",
            severity=_severity(final_score),
            severity_score=round(final_score, 4),
            risk_score=round(final_score, 4),
            priority_level="CRITICAL",
            track_ids=primary.track_ids + [track.track_id for track in people],
            track_ref_ids=primary.track_ref_ids + [track.track_uuid for track in people],
            identity_ids=primary.identity_ids + [track.identity_id for track in people if track.identity_id],
            camera_ids=[packet.camera_id],
            frame_range=(packet.frame_id, packet.frame_id),
            confidence_score=round(final_score, 4),
            time_window=(packet.frame_id / 30.0, packet.frame_id / 30.0),
            confidence_distribution={"person_count": len(people), "weapon_events": len(weapons)},
            timestamp=packet.timestamp,
            metadata={"person_count": len(people), "source_event_id": primary.event_id},
        )
        return [event]

    def _score_track(self, packet: FramePacket, track: Track, label: str) -> tuple[float, dict[str, float]]:
        width = packet.frame_width or (packet.image.shape[1] if packet.image is not None else 640)
        height = packet.frame_height or (packet.image.shape[0] if packet.image is not None else 640)
        persistence = track.stability_score
        spatial_risk = self._spatial_risk(track, width, height)
        motion_anomaly = self._motion_anomaly(track)
        class_weight = _CLASS_WEIGHTS.get(label, _DEFAULT_CLASS_WEIGHT)
        raw_score = (
            0.30 * persistence
            + 0.25 * spatial_risk
            + 0.20 * motion_anomaly
            + 0.25 * class_weight
        )
        score = self._apply_decay(track, packet.timestamp, raw_score)
        components = {
            "persistence_score": round(persistence, 4),
            "spatial_risk": round(spatial_risk, 4),
            "motion_anomaly": round(motion_anomaly, 4),
            "class_weight": round(class_weight, 4),
        }
        return round(score, 4), components

    def _apply_decay(self, track: Track, timestamp: str, raw_score: float) -> float:
        key = track.identity_id or f"{track.camera_id}:{track.track_id}"
        current_time = _parse_timestamp(timestamp)
        previous_score, previous_time = self._score_memory.get(key, (0.0, current_time))
        delta_seconds = max(0.0, (current_time - previous_time).total_seconds())
        decayed_score = previous_score * math.exp(-_DECAY_LAMBDA * delta_seconds)
        blended = min(1.0, max(raw_score, raw_score + 0.25 * decayed_score))
        self._score_memory[key] = (blended, current_time)
        return blended

    @staticmethod
    def _spatial_risk(track: Track, frame_width: int, frame_height: int) -> float:
        bbox = track.bbox
        cx = (bbox[0] + bbox[2]) / 2.0 / max(1, frame_width)
        cy = (bbox[1] + bbox[3]) / 2.0 / max(1, frame_height)
        area_ratio = (
            max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
        ) / max(1, frame_width * frame_height)
        centrality = max(0.0, 1.0 - 2.0 * math.sqrt((cx - 0.5) ** 2 + (cy - 0.5) ** 2))
        return min(1.0, 0.55 * centrality + 0.45 * min(1.0, area_ratio * 10.0))

    @staticmethod
    def _motion_anomaly(track: Track) -> float:
        vx = track.velocity[0] if len(track.velocity) > 0 else 0.0
        vy = track.velocity[1] if len(track.velocity) > 1 else 0.0
        speed = math.sqrt(vx * vx + vy * vy)
        return min(1.0, speed / 35.0)

    def _adaptive_threshold(self, scene_density: float, track_count: int) -> float:
        """
        threshold = base_density_threshold + noise_factor + stream_load_factor

        base_density_threshold  scales with scene_density (existing logic).
        noise_factor            rises when recent events had low risk scores,
                                indicating the engine may be firing on noise.
        stream_load_factor      rises with avg detections per frame; dense
                                scenes produce more spurious detections.
        """
        # Base: scene-density + track-count scaling (unchanged from Phase 4)
        if scene_density >= 0.60:
            base = min(0.75, _BASE_THRESHOLD + 0.10 + 0.01 * track_count)
        elif scene_density <= 0.20:
            base = max(0.22, _BASE_THRESHOLD - 0.08)
        else:
            base = min(0.70, _BASE_THRESHOLD + 0.04 * scene_density + 0.004 * track_count)

        noise = self._noise_factor()
        load = self._stream_load_factor()
        return round(max(0.25, min(0.75, base + noise + load)), 4)

    def _noise_factor(self) -> float:
        """
        Fraction of recent events that scored in the [base, base+0.15] band
        (barely above threshold) × 0.10 scaling cap.  High ratio ⟹ noisy
        detector ⟹ raise threshold.
        """
        if not self._recent_event_scores:
            return 0.0
        low_band = sum(
            1 for s in self._recent_event_scores
            if _BASE_THRESHOLD <= s < _BASE_THRESHOLD + 0.15
        )
        ratio = low_band / len(self._recent_event_scores)
        return round(min(0.08, ratio * 0.12), 4)

    def _stream_load_factor(self) -> float:
        """
        avg_detections_per_frame × 0.003, capped at +0.06.
        More detections ⟹ more spurious matches ⟹ stricter threshold.
        """
        if not self._recent_det_counts:
            return 0.0
        avg = sum(self._recent_det_counts) / len(self._recent_det_counts)
        return round(min(0.06, avg * 0.003), 4)

    @staticmethod
    def _compute_priority(event_type: str, track: Track) -> str:
        """
        Assign priority_level from event type and track attributes.

        Rules (highest wins):
            ARMED_CROWD_THREAT              → CRITICAL
            WEAPON_THREAT + known identity  → HIGH
            WEAPON_THREAT (no identity)     → MEDIUM
            PHONE_USAGE_RISK                → LOW
        """
        if event_type == "ARMED_CROWD_THREAT":
            return "CRITICAL"
        if event_type == "WEAPON_THREAT":
            if track.identity_id is not None:
                return "HIGH"
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _build_event(
        packet: FramePacket,
        track: Track,
        score: float,
        event_type: str,
        components: dict[str, float],
    ) -> Event:
        return Event(
            event_type=event_type,
            severity=_severity(score),
            severity_score=round(score, 4),
            risk_score=round(score, 4),
            priority_level=EventEngine._compute_priority(event_type, track),
            track_ids=[track.track_id],
            track_ref_ids=[track.track_uuid],
            identity_ids=[track.identity_id] if track.identity_id else [],
            camera_ids=[packet.camera_id],
            frame_range=(packet.frame_id, packet.frame_id),
            confidence_score=track.confidence,
            contributing_tracks=[track.to_dict()],
            time_window=(packet.frame_id / 30.0, packet.frame_id / 30.0),
            confidence_distribution={track.class_name: track.confidence},
            timestamp=packet.timestamp,
            metadata=components,
        )


_LEGACY_WEAPON_LABELS = frozenset({"weapon", "pistol", "rifle", "knife", "grenade", "shotgun", "gun", "sword"})
_LEGACY_CROWD_THRESHOLD = 5


def evaluate(result: DetectionResult) -> dict | None:
    """Legacy function-based evaluate. Kept for backwards compatibility."""
    labels = [obj.type for obj in result.objects]
    weapons = sorted({label for label in labels if label in _LEGACY_WEAPON_LABELS})
    if weapons:
        return {
            "event_type": "WEAPON_DETECTED",
            "severity": "high",
            "detail": f"Detected: {', '.join(weapons)}",
        }
    if labels.count("person") > _LEGACY_CROWD_THRESHOLD:
        return {
            "event_type": "CROWD_ALERT",
            "severity": "medium",
            "detail": (
                f"Person count {labels.count('person')} exceeds threshold {_LEGACY_CROWD_THRESHOLD}"
            ),
        }
    return None
