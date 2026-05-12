from __future__ import annotations

import json
import logging
import math
from collections import deque
from datetime import datetime, timezone
from typing import List

from cachetools import TTLCache

from core.event_bus import EventType, get_event_bus
from inference.event_buffer import EventBuffer
from inference.config_runtime import load_runtime_config
from inference.identity_db import IdentityDB, get_db
from inference.monitoring.metrics import get_metrics
from inference.schemas import DetectionResult, Event, FramePacket, Track

logger = logging.getLogger(__name__)

_CLASS_WEIGHTS: dict[str, float] = {
    # Weapon sub-classes (preserved after removing normalisation)
    "weapon": 0.95,
    "pistol": 0.95,
    "rifle": 0.95,
    "knife": 0.85,
    "grenade": 0.98,
    "gun": 0.95,
    "shotgun": 0.95,
    "sword": 0.80,
    # Distraction / contextual
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

# Loitering
_LOITERING_SPEED_THRESHOLD = 0.1   # pixels/frame — below this is "stationary"

# Unattended object
_UNATTENDED_FRAME_THRESHOLD = 30   # consecutive frames without a nearby person
_PERSON_PROXIMITY_IOU = 0.05       # IoU threshold for "person is nearby"


def _parse_timestamp(timestamp: str) -> datetime:
    try:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
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

    Detects the following event types:
      WEAPON_THREAT          — confirmed weapon track above risk threshold
      PHONE_USAGE_RISK       — phone track with optional person proximity bonus
      ARMED_CROWD_THREAT     — weapon event + 3+ persons in the same frame
      LOITERING_DETECTED     — person stationary beyond loitering_threshold_seconds
      UNATTENDED_OBJECT      — non-person object present without nearby person
                               for >= _UNATTENDED_FRAME_THRESHOLD frames
      GEOFENCE_VIOLATION     — any track centre inside a restricted zone polygon

    Args:
        db:                         IdentityDB instance (or None for default singleton).
        loitering_threshold_seconds: Seconds a person must be nearly stationary
                                    before a LOITERING_DETECTED event fires.
        restricted_zones:           List of polygons, each a list of [x, y] points
                                    in pixel coordinates, read from scenario config
                                    rules.restricted_zones.
    """

    def __init__(
        self,
        db: IdentityDB | None = None,
        loitering_threshold_seconds: float = 30.0,
        restricted_zones: list | None = None,
    ) -> None:
        self._db = db or get_db()
        cfg = _event_engine_config()
        self._class_weights = dict(cfg.get("class_weights", _CLASS_WEIGHTS))
        self._default_class_weight = float(cfg.get("default_class_weight", _DEFAULT_CLASS_WEIGHT))
        thresholds = cfg.get("thresholds", {})
        self._base_threshold = float(thresholds.get("base", _BASE_THRESHOLD))
        self._weapon_threshold = float(thresholds.get("weapon", _WEAPON_THRESHOLD))
        self._phone_threshold = float(thresholds.get("phone", _PHONE_THRESHOLD))
        self._decay_lambda = float(thresholds.get("decay_lambda", _DECAY_LAMBDA))
        self._weapon_confirmation = int(thresholds.get("weapon_confirmation_frames", _WEAPON_CONFIRMATION))
        self._phone_confirmation = int(thresholds.get("phone_confirmation_frames", _PHONE_CONFIRMATION))
        self._unattended_frame_threshold = int(thresholds.get("unattended_frame_threshold", _UNATTENDED_FRAME_THRESHOLD))
        self._person_proximity_iou = float(thresholds.get("person_proximity_iou", _PERSON_PROXIMITY_IOU))
        self._scoring_weights = dict(cfg.get("scoring_weights", {
            "persistence": 0.30,
            "spatial": 0.25,
            "motion": 0.20,
            "class": 0.25,
        }))

        # TTL-bounded score memory prevents unbounded growth.
        # Entries expire after 300 s of inactivity; max 10 000 live entries.
        self._score_memory: TTLCache = TTLCache(maxsize=10_000, ttl=300)

        # Phase 5 — adaptive threshold state
        self._recent_event_scores: deque[float] = deque(maxlen=30)
        self._recent_det_counts: deque[int] = deque(maxlen=20)

        # Behaviour detection config
        self._loitering_threshold_seconds = loitering_threshold_seconds
        self._restricted_zones: list = restricted_zones or []

        # Unattended object registry: track_id → consecutive unattended frames
        self._unattended_registry: dict[int, int] = {}

        # Object ownership map: object_track_id → person_track_id assigned at first detection
        self._object_owner_map: dict[int, int] = {}

    # ── main evaluate entry point ─────────────────────────────────────────────

    def evaluate(self, buffer: EventBuffer) -> list[Event]:
        if len(buffer) == 0:
            return []
        recent = buffer.get_recent(1)
        if not recent:
            return []
        packet = recent[-1]

        self._recent_det_counts.append(len(packet.detections))
        threshold = self._adaptive_threshold(buffer.get_scene_density(), len(packet.tracks))
        tracks = [track for track in packet.tracks if track.missed_frames == 0]

        events: list[Event] = []
        events.extend(self._weapon_events(packet, tracks, buffer, threshold))
        events.extend(self._phone_events(packet, tracks, buffer, threshold))
        events.extend(self._crowd_events(packet, tracks, events))
        events.extend(self._loitering_events(packet, tracks, buffer))
        events.extend(self._unattended_object_events(packet, tracks))
        events.extend(self._geofence_events(packet, tracks))
        active_tracks = {track.track_id for track in tracks}

        for event in events:
            for track_id in event.track_ids:
                if track_id not in active_tracks:
                    logger.error("Invalid event: track not found")
            self._db.persist_event(event, frame_id=packet.frame_id)
            self._recent_event_scores.append(event.risk_score)
            get_event_bus().publish(EventType.THREAT_EVENT, event, source=packet.camera_id, priority=_event_priority_value(event))

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

    # ── existing event generators ─────────────────────────────────────────────

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
            if series is None or series.duration_frames < self._weapon_confirmation:
                continue
            score, components = self._score_track(packet, track, track.class_name)
            if series.threat_score_series:
                series.threat_score_series[-1] = score
            if score < max(threshold, self._weapon_threshold):
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
            if series is None or series.duration_frames < self._phone_confirmation:
                continue
            base_score, components = self._score_track(packet, track, "phone")
            if series.threat_score_series:
                series.threat_score_series[-1] = base_score
            proximity = max((_iou(track.bbox, person.bbox) for person in person_tracks), default=0.0)
            final_score = min(1.0, base_score + 0.20 * proximity)
            if final_score < min(max(0.24, threshold - 0.05), self._phone_threshold):
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
            metadata=self._event_metadata(packet, {"person_count": len(people), "source_event_id": primary.event_id}),
        )
        return [event]

    # ── new event generators ──────────────────────────────────────────────────

    def _loitering_events(
        self,
        packet: FramePacket,
        tracks: list[Track],
        buffer: EventBuffer,
    ) -> list[Event]:
        """
        Fire LOITERING_DETECTED for any person track that has been nearly
        stationary for longer than _loitering_threshold_seconds.

        Stationarity is measured via sliding-window motion variance computed
        from the track's bbox_series (up to 30 most-recent confirmed frames).
        loiter_score = dwell_factor * (1 - normalized_motion_variance).

        Tracks whose centre falls inside a restricted zone are skipped because
        a GEOFENCE_VIOLATION event takes precedence.
        """
        events: list[Event] = []
        for track in tracks:
            if track.class_name != "person":
                continue

            # Skip if inside any restricted zone — geofence violation is the primary signal.
            bbox = track.bbox
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            if self._in_any_zone(cx, cy):
                continue

            try:
                first = _parse_timestamp(track.first_seen_at)
                last = _parse_timestamp(track.last_seen_at)
                duration_secs = max(0.0, (last - first).total_seconds())
            except Exception:
                continue

            if duration_secs < self._loitering_threshold_seconds:
                continue

            # Sliding-window motion variance from the track series.
            series = buffer.get_track_series(track.track_id)
            if series is not None and len(series.bbox_series) >= 5:
                recent = series.bbox_series[-30:]
                centers = [
                    ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
                    for b in recent
                ]
                speeds = [
                    math.sqrt(
                        (centers[i][0] - centers[i - 1][0]) ** 2
                        + (centers[i][1] - centers[i - 1][1]) ** 2
                    )
                    for i in range(1, len(centers))
                ]
                mean_speed = sum(speeds) / len(speeds)
                variance = sum((s - mean_speed) ** 2 for s in speeds) / len(speeds)
                # Normalise: 100 px²/frame² treated as maximum variance.
                normalized_variance = min(1.0, variance / 100.0)
            else:
                # Fall back to EMA velocity magnitude when series is too short.
                vx = track.velocity[0] if len(track.velocity) > 0 else 0.0
                vy = track.velocity[1] if len(track.velocity) > 1 else 0.0
                speed_mag = math.sqrt(vx * vx + vy * vy)
                normalized_variance = min(1.0, speed_mag / 5.0)

            dwell_factor = min(1.0, duration_secs / 300.0)
            loiter_score = dwell_factor * (1.0 - normalized_variance)
            score = min(0.70, 0.25 + 0.45 * loiter_score)

            if score < 0.26:
                continue

            events.append(Event(
                event_type="LOITERING_DETECTED",
                severity=_severity(score),
                severity_score=round(score, 4),
                risk_score=round(score, 4),
                priority_level="MEDIUM",
                track_ids=[track.track_id],
                track_ref_ids=[track.track_uuid],
                identity_ids=[track.identity_id] if track.identity_id else [],
                camera_ids=[packet.camera_id],
                frame_range=(packet.frame_id, packet.frame_id),
                confidence_score=track.confidence,
                time_window=(packet.frame_id / 30.0, packet.frame_id / 30.0),
                timestamp=packet.timestamp,
                metadata=self._event_metadata(packet, {
                    "duration_seconds": round(duration_secs, 1),
                    "loiter_score": round(loiter_score, 4),
                    "normalized_motion_variance": round(normalized_variance, 4),
                    "threshold_seconds": self._loitering_threshold_seconds,
                }),
            ))
        return events

    def _unattended_object_events(
        self,
        packet: FramePacket,
        tracks: list[Track],
    ) -> list[Event]:
        """
        Fire UNATTENDED_OBJECT when a non-person track has been separated from
        its owner person for at least _UNATTENDED_FRAME_THRESHOLD consecutive frames.

        Ownership is assigned at the object's first appearance: the nearest person
        by IoU becomes the owner.  Subsequent frames check whether that specific
        person is still present in the active track set.  Objects that were spawned
        without any nearby person fall back to the IoU proximity check.

        Registry entries for tracks that leave the active set are purged to avoid
        stale counters accumulating in memory.
        """
        events: list[Event] = []
        person_tracks = [t for t in tracks if t.class_name == "person"]
        object_tracks = [t for t in tracks if t.class_name != "person"]

        active_ids = {t.track_id for t in tracks}
        person_ids = {t.track_id for t in person_tracks}

        for track in object_tracks:
            # Assign an owner person the first time this object is seen.
            if track.track_id not in self._object_owner_map:
                best_iou = 0.0
                best_person_id: int | None = None
                for p in person_tracks:
                    iou = _iou(track.bbox, p.bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_person_id = p.track_id
                if best_person_id is not None:
                    self._object_owner_map[track.track_id] = best_person_id

            owner_id = self._object_owner_map.get(track.track_id)

            if owner_id is not None:
                # Owner-based check: is the assigned person still active?
                if owner_id in person_ids:
                    self._unattended_registry.pop(track.track_id, None)
                    continue
                # Owner has left the scene → increment unattended counter.
                self._unattended_registry[track.track_id] = (
                    self._unattended_registry.get(track.track_id, 0) + 1
                )
            else:
                # No owner assigned (object appeared without any nearby person).
                # Fall back to per-frame IoU proximity check.
                nearby = any(
                    _iou(track.bbox, p.bbox) > self._person_proximity_iou
                    for p in person_tracks
                )
                if nearby:
                    self._unattended_registry.pop(track.track_id, None)
                    continue
                self._unattended_registry[track.track_id] = (
                    self._unattended_registry.get(track.track_id, 0) + 1
                )

            count = self._unattended_registry.get(track.track_id, 0)
            if count < self._unattended_frame_threshold:
                continue

            score = min(1.0, 0.40 + 0.20 * min(1.0, count / (3 * self._unattended_frame_threshold)))
            events.append(Event(
                event_type="UNATTENDED_OBJECT",
                severity=_severity(score),
                severity_score=round(score, 4),
                risk_score=round(score, 4),
                priority_level="MEDIUM",
                track_ids=[track.track_id],
                track_ref_ids=[track.track_uuid],
                identity_ids=[],
                camera_ids=[packet.camera_id],
                frame_range=(packet.frame_id, packet.frame_id),
                confidence_score=track.confidence,
                time_window=(packet.frame_id / 30.0, packet.frame_id / 30.0),
                timestamp=packet.timestamp,
                metadata=self._event_metadata(packet, {
                    "object_class": track.class_name,
                    "owner_track_id": owner_id,
                    "unattended_frames": count,
                    "threshold_frames": self._unattended_frame_threshold,
                }),
            ))

        # Purge stale entries for tracks no longer in the active set.
        for tid in [tid for tid in list(self._unattended_registry) if tid not in active_ids]:
            del self._unattended_registry[tid]
        for tid in [tid for tid in list(self._object_owner_map) if tid not in active_ids]:
            del self._object_owner_map[tid]

        return events

    def _geofence_events(
        self,
        packet: FramePacket,
        tracks: list[Track],
    ) -> list[Event]:
        """
        Fire GEOFENCE_VIOLATION when any track's bounding-box centre falls
        inside a restricted zone polygon.

        Supports two zone formats:
          Legacy:   [[x, y], [x, y], ...]                       — plain polygon
          Semantic: {"zone": [[x, y], ...],                      — polygon
                     "allowed_objects": ["person"],              — classes that may enter freely
                     "active_hours": [8, 20]}                    — UTC hour window [start, end)

        Semantic zones skip the event when:
          • the track's class is listed in allowed_objects, OR
          • the current UTC hour is outside active_hours.

        One event is emitted per (track, zone) pair per frame; the first
        matching zone terminates the inner loop for that track.
        """
        if not self._restricted_zones:
            return []

        current_hour = datetime.now(timezone.utc).hour
        events: list[Event] = []

        for track in tracks:
            bbox = track.bbox
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0

            for zone_idx, zone_entry in enumerate(self._restricted_zones):
                # Parse zone format — dict (semantic) or list (legacy).
                if isinstance(zone_entry, dict):
                    polygon = zone_entry.get("zone", [])
                    allowed_objects: list | None = zone_entry.get("allowed_objects")
                    active_hours: list | None = zone_entry.get("active_hours")
                else:
                    polygon = zone_entry
                    allowed_objects = None
                    active_hours = None

                if len(polygon) < 3:
                    continue

                # Hour-window gate: skip if zone is not active right now.
                if active_hours is not None and len(active_hours) >= 2:
                    start_h, end_h = int(active_hours[0]), int(active_hours[1])
                    if start_h <= end_h:
                        if not (start_h <= current_hour < end_h):
                            continue
                    else:  # window wraps midnight, e.g. [22, 6)
                        if not (current_hour >= start_h or current_hour < end_h):
                            continue

                # Allowed-object gate: object class is permitted inside this zone.
                if allowed_objects is not None and track.class_name in allowed_objects:
                    continue

                if not self._point_in_polygon((cx, cy), polygon):
                    continue

                class_w = self._class_weights.get(track.class_name, self._default_class_weight)
                score = min(1.0, 0.55 + 0.20 * class_w)
                events.append(Event(
                    event_type="GEOFENCE_VIOLATION",
                    severity=_severity(score),
                    severity_score=round(score, 4),
                    risk_score=round(score, 4),
                    priority_level="HIGH",
                    track_ids=[track.track_id],
                    track_ref_ids=[track.track_uuid],
                    identity_ids=[track.identity_id] if track.identity_id else [],
                    camera_ids=[packet.camera_id],
                    frame_range=(packet.frame_id, packet.frame_id),
                    confidence_score=track.confidence,
                    time_window=(packet.frame_id / 30.0, packet.frame_id / 30.0),
                    timestamp=packet.timestamp,
                    metadata=self._event_metadata(packet, {
                        "zone_index": zone_idx,
                        "object_class": track.class_name,
                        "center_px": [round(cx, 1), round(cy, 1)],
                        "allowed_objects": allowed_objects,
                        "active_hours": active_hours,
                    }),
                ))
                break  # one violation per track per frame (first matching zone)

        return events

    def _in_any_zone(self, cx: float, cy: float) -> bool:
        """Return True if (cx, cy) falls inside any configured restricted zone."""
        for zone_entry in self._restricted_zones:
            polygon = (
                zone_entry.get("zone", [])
                if isinstance(zone_entry, dict)
                else zone_entry
            )
            if len(polygon) >= 3 and self._point_in_polygon((cx, cy), polygon):
                return True
        return False

    @staticmethod
    def _point_in_polygon(
        point: tuple[float, float],
        polygon: list[list[float]],
    ) -> bool:
        """
        Ray-casting point-in-polygon test.

        Args:
            point:   (x, y) in pixel coordinates.
            polygon: List of [x, y] vertices.  Must have at least 3 points.

        Returns:
            True if *point* is strictly inside *polygon*.
        """
        x, y = point
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = float(polygon[i][0]), float(polygon[i][1])
            xj, yj = float(polygon[j][0]), float(polygon[j][1])
            # Edge crosses the horizontal ray from point to the right
            if (yi > y) != (yj > y):
                x_intersect = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
                if x < x_intersect:
                    inside = not inside
            j = i
        return inside

    # ── scoring helpers ───────────────────────────────────────────────────────

    def _score_track(self, packet: FramePacket, track: Track, label: str) -> tuple[float, dict[str, float]]:
        width = packet.frame_width or (packet.image.shape[1] if packet.image is not None else 640)
        height = packet.frame_height or (packet.image.shape[0] if packet.image is not None else 640)
        persistence = track.stability_score
        spatial_risk = self._spatial_risk(track, width, height)
        motion_anomaly = self._motion_anomaly(track)
        class_weight = self._class_weights.get(label, self._default_class_weight)
        persistence_w = float(self._scoring_weights.get("persistence", 0.30))
        spatial_w = float(self._scoring_weights.get("spatial", 0.25))
        motion_w = float(self._scoring_weights.get("motion", 0.20))
        class_w = float(self._scoring_weights.get("class", 0.25))
        raw_score = (
            persistence_w * persistence
            + spatial_w * spatial_risk
            + motion_w * motion_anomaly
            + class_w * class_weight
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
        decayed_score = previous_score * math.exp(-self._decay_lambda * delta_seconds)
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
        if scene_density >= 0.60:
            base = min(0.75, self._base_threshold + 0.10 + 0.01 * track_count)
        elif scene_density <= 0.20:
            base = max(0.22, self._base_threshold - 0.08)
        else:
            base = min(0.70, self._base_threshold + 0.04 * scene_density + 0.004 * track_count)

        noise = self._noise_factor()
        load = self._stream_load_factor()
        return round(max(0.25, min(0.75, base + noise + load)), 4)

    def _noise_factor(self) -> float:
        if not self._recent_event_scores:
            return 0.0
        low_band = sum(
            1 for s in self._recent_event_scores
            if self._base_threshold <= s < self._base_threshold + 0.15
        )
        ratio = low_band / len(self._recent_event_scores)
        return round(min(0.08, ratio * 0.12), 4)

    def _stream_load_factor(self) -> float:
        if not self._recent_det_counts:
            return 0.0
        avg = sum(self._recent_det_counts) / len(self._recent_det_counts)
        return round(min(0.06, avg * 0.003), 4)

    @staticmethod
    def _compute_priority(event_type: str, track: Track) -> str:
        if event_type == "ARMED_CROWD_THREAT":
            return "CRITICAL"
        if event_type == "WEAPON_THREAT":
            if track.identity_id is not None:
                return "HIGH"
            return "MEDIUM"
        if event_type == "GEOFENCE_VIOLATION":
            return "HIGH"
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
            metadata=EventEngine._event_metadata(packet, components),
        )

    @staticmethod
    def _event_metadata(packet: FramePacket, extra: dict | None = None) -> dict:
        packet_meta = dict(packet.metadata or {})
        source_type = str(packet_meta.get("source_type") or "live_stream")
        payload = {
            **dict(extra or {}),
            "source_type": source_type,
            "simulated": bool(packet_meta.get("simulated", False)),
        }
        if packet_meta.get("drone_id"):
            payload["drone_id"] = packet_meta.get("drone_id")
        if source_type == "drone_simulation":
            payload.setdefault("safe_label", "Simulated aerial observation")
        return payload


def _event_engine_config() -> dict:
    try:
        cfg = load_runtime_config("incident_rules")
    except FileNotFoundError:
        return {}
    event_cfg = cfg.get("event_engine", {})
    return event_cfg if isinstance(event_cfg, dict) else {}


def _event_priority_value(event: Event) -> int:
    return {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 5, "LOW": 7}.get(
        str(event.priority_level or event.severity or "LOW").upper(),
        7,
    )


# ── legacy function interface ─────────────────────────────────────────────────

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
