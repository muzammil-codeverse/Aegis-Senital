from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

import numpy as np

from inference.identity_db import (
    IdentityDB,
    SCENARIO_ACTIVE,
    SCENARIO_ESCALATING,
    SCENARIO_FALSE_ALARM,
    SCENARIO_RESOLVED,
    get_db,
)
from inference.schemas import DetectionResult, Event, Scenario
from ml.llm.external_reasoning import ExternalReasoningEngine

logger = logging.getLogger(__name__)

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_SCENARIO_LABELS = {
    0: "NORMAL_ACTIVITY",
    1: "SUSPICIOUS_ACTIVITY",
    2: "ARMED_INDIVIDUAL",
    3: "CROWD_THREAT",
}

# Phase 5 — escalation pattern detection
# Each tuple: (required event_types in history, escalation_level)
# Checked in order; first match wins.
_ESCALATION_PATTERNS: list[tuple[list[str], str]] = [
    (["WEAPON_THREAT", "ARMED_CROWD_THREAT"], "CRITICAL"),
    (["WEAPON_THREAT", "PHONE_USAGE_RISK", "ARMED_CROWD_THREAT"], "CRITICAL"),
    (["WEAPON_THREAT", "PHONE_USAGE_RISK"], "HIGH"),
    (["WEAPON_THREAT", "WEAPON_THREAT"], "HIGH"),   # repeated weapon sightings
    (["PHONE_USAGE_RISK", "WEAPON_THREAT"], "HIGH"),
    (["WEAPON_THREAT"], "MEDIUM"),
    (["PHONE_USAGE_RISK", "PHONE_USAGE_RISK"], "LOW"),
]
_IDENTITY_HISTORY_LEN = 20   # event types retained per identity


def _cosine(left: list[float], right: list[float]) -> float:
    lhs = np.asarray(left, dtype=np.float32).reshape(-1)
    rhs = np.asarray(right, dtype=np.float32).reshape(-1)
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


def _score_to_risk(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"
    if score >= 0.60:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


class ScenarioClassifier:
    """
    Deterministic scenario classifier.
    """

    def predict(self, cluster: list[Event], features: dict[str, float]) -> str:
        return self._heuristic(cluster, features)

    @staticmethod
    def _heuristic(cluster: list[Event], features: dict[str, float]) -> str:
        event_types = {event.event_type for event in cluster}
        if "ARMED_CROWD_THREAT" in event_types or features["person_count"] >= 3.0 and features["weapon_events"] > 0.0:
            return "CROWD_THREAT"
        if "WEAPON_THREAT" in event_types or features["weapon_events"] > 0.0:
            return "ARMED_INDIVIDUAL"
        if features["event_count"] > 1.0 or features["multi_camera"] > 0.0:
            return "SUSPICIOUS_ACTIVITY"
        return "NORMAL_ACTIVITY"


class ScenarioEngine:
    """
    Event-vector clustering and scenario classification engine.
    """

    def __init__(
        self,
        fps: float = 25.0,
        time_window_secs: float = 7.5,
        db: IdentityDB | None = None,
        reasoner: ExternalReasoningEngine | None = None,
    ) -> None:
        self._frame_window = max(1, int(fps * time_window_secs))
        self._db = db or get_db()
        self._classifier = ScenarioClassifier()
        self._reasoner = reasoner or ExternalReasoningEngine()
        self._known_signatures: dict[str, str] = {}
        # Phase 5 — per-identity event history for temporal reasoning
        self._identity_event_history: dict[str, deque[str]] = {}

    def aggregate(self, event_list: list[Event]) -> list[Scenario]:
        persisted_events = [event for event in event_list if getattr(event, "persisted", False)]
        if not persisted_events:
            return []

        # Update per-identity event history before clustering
        self._update_identity_history(persisted_events)

        vectors = [self._event_vector(event) for event in persisted_events]
        clusters = self._cluster_events(persisted_events, vectors)
        scenarios: list[Scenario] = []

        for cluster in clusters:
            features = self._cluster_features(cluster)
            scenario_type = self._classifier.predict(cluster, features)
            confidence = round(sum(event.risk_score for event in cluster) / len(cluster), 4)
            risk_level = self._derive_risk_level(scenario_type, confidence, features)
            status = self._derive_status(cluster, scenario_type, confidence)
            frame_start = min(event.frame_range[0] for event in cluster)
            frame_end = max(event.frame_range[1] for event in cluster)
            identity_ids = sorted({identity_id for event in cluster for identity_id in event.identity_ids})
            camera_ids = sorted({camera_id for event in cluster for camera_id in event.camera_ids})

            # Phase 5 — temporal reasoning: detect escalation across identities
            escalation_level = self._detect_escalation(
                identity_ids,
                {event.event_type for event in cluster},
            )

            scenario = Scenario(
                scenario_type=scenario_type,
                events=cluster,
                risk_level=risk_level,
                summary=self._summary(scenario_type, cluster, confidence),
                temporal_span=(frame_start, frame_end),
                confidence_score=confidence,
                event_cluster=cluster,
                status=status,
                camera_ids=camera_ids,
                identity_ids=identity_ids,
                scenario_vector=self._cluster_vector(cluster),
                escalation_level=escalation_level,
                metadata={"features": features},
            )
            scenario.start_time = min(event.timestamp for event in cluster)
            scenario.end_time = max(event.timestamp for event in cluster)
            reasoning = self._reasoner.explain(scenario.to_dict(), [event.to_dict() for event in cluster])
            scenario.metadata["reasoning"] = reasoning
            self._db.persist_scenario(scenario)
            scenarios.append(scenario)
            self._known_signatures[self._signature(scenario_type, identity_ids, camera_ids)] = risk_level

            logger.info(
                json.dumps(
                    {
                        "event": "scenario_generated",
                        "scenario_id": scenario.scenario_id,
                        "scenario_type": scenario_type,
                        "risk_level": risk_level,
                        "escalation_level": escalation_level,
                        "status": status,
                        "event_count": len(cluster),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                )
            )

        scenarios.sort(key=lambda scenario: _RISK_ORDER.get(scenario.risk_level, 0), reverse=True)
        return scenarios

    # ── Phase 5: temporal reasoning helpers ───────────────────────────────────

    def _update_identity_history(self, events: list[Event]) -> None:
        """Append each event's type to the history deque of its associated identities."""
        for event in events:
            for identity_id in event.identity_ids:
                history = self._identity_event_history.setdefault(
                    identity_id,
                    deque(maxlen=_IDENTITY_HISTORY_LEN),
                )
                history.append(event.event_type)

    def _detect_escalation(
        self,
        identity_ids: list[str],
        current_event_types: set[str],
    ) -> str:
        """
        Check whether any tracked identity has accumulated an escalation
        pattern in its event history.  Current cluster events are appended
        to the accumulated history before matching.

        Returns the highest matching escalation_level, or "NONE".
        """
        # Collect the combined history for all involved identities
        combined: list[str] = []
        for iid in identity_ids:
            combined.extend(self._identity_event_history.get(iid, []))
        combined.extend(current_event_types)  # include current frame events

        combined_set = set(combined)
        for required_types, level in _ESCALATION_PATTERNS:
            if all(rtype in combined_set for rtype in required_types):
                return level
        return "NONE"

    def resolve_scenario(self, scenario_id: str) -> None:
        self._db.update_scenario_status(scenario_id, SCENARIO_RESOLVED)

    def mark_false_alarm(self, scenario_id: str) -> None:
        self._db.update_scenario_status(scenario_id, SCENARIO_FALSE_ALARM)

    def _cluster_events(self, events: list[Event], vectors: list[list[float]]) -> list[list[Event]]:
        parent = list(range(len(events)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[left_root] = right_root

        for left in range(len(events)):
            for right in range(left + 1, len(events)):
                if self._related(events[left], events[right], vectors[left], vectors[right]):
                    union(left, right)

        groups: dict[int, list[Event]] = defaultdict(list)
        for index, event in enumerate(events):
            groups[find(index)].append(event)
        return list(groups.values())

    def _related(self, left: Event, right: Event, left_vector: list[float], right_vector: list[float]) -> bool:
        shared_identity = bool(set(left.identity_ids) & set(right.identity_ids))
        shared_camera = bool(set(left.camera_ids) & set(right.camera_ids))
        temporal_close = abs(left.frame_range[0] - right.frame_range[0]) <= self._frame_window
        similarity = _cosine(left_vector, right_vector)
        return shared_identity or (temporal_close and (similarity >= 0.82 or shared_camera))

    def _event_vector(self, event: Event) -> list[float]:
        class_embedding = self._class_embedding(event.event_type)
        spatial_features = self._spatial_features(event)
        temporal_features = self._temporal_features(event)
        identity_embedding = self._identity_embedding(event)
        vector = class_embedding + spatial_features + temporal_features + identity_embedding
        return vector

    @staticmethod
    def _class_embedding(event_type: str) -> list[float]:
        event_type = event_type.upper()
        return [
            1.0 if "WEAPON" in event_type else 0.0,
            1.0 if "PHONE" in event_type else 0.0,
            1.0 if "CROWD" in event_type else 0.0,
            1.0 if "THREAT" in event_type else 0.0,
        ]

    @staticmethod
    def _spatial_features(event: Event) -> list[float]:
        track_payload = event.contributing_tracks[0] if event.contributing_tracks else {}
        bbox = track_payload.get("bbox", [0.0, 0.0, 0.0, 0.0])
        width = max(0.0, bbox[2] - bbox[0])
        height = max(0.0, bbox[3] - bbox[1])
        center_x = (bbox[0] + bbox[2]) / 2.0
        center_y = (bbox[1] + bbox[3]) / 2.0
        return [center_x / 640.0, center_y / 640.0, width / 640.0, height / 640.0]

    @staticmethod
    def _temporal_features(event: Event) -> list[float]:
        start, end = event.frame_range
        start_seconds, end_seconds = event.time_window
        return [
            start / 300.0,
            end / 300.0,
            max(0.0, end_seconds - start_seconds),
            event.risk_score,
        ]

    @staticmethod
    def _identity_embedding(event: Event) -> list[float]:
        track_payload = event.contributing_tracks[0] if event.contributing_tracks else {}
        face = track_payload.get("face_embedding", [])[:8]
        appearance = track_payload.get("appearance_embedding", [])[:8]
        face = face + [0.0] * (8 - len(face))
        appearance = appearance + [0.0] * (8 - len(appearance))
        return list(face) + list(appearance)

    def _cluster_features(self, cluster: list[Event]) -> dict[str, float]:
        return {
            "event_count": float(len(cluster)),
            "mean_risk": float(sum(event.risk_score for event in cluster) / len(cluster)),
            "max_risk": float(max(event.risk_score for event in cluster)),
            "weapon_events": float(sum(1 for event in cluster if "WEAPON" in event.event_type)),
            "phone_events": float(sum(1 for event in cluster if "PHONE" in event.event_type)),
            "person_count": float(
                max(
                    (
                        event.metadata.get("person_count", 0)
                        for event in cluster
                        if isinstance(event.metadata, dict)
                    ),
                    default=0,
                )
            ),
            "identity_count": float(len({identity_id for event in cluster for identity_id in event.identity_ids})),
            "multi_camera": float(len({camera_id for event in cluster for camera_id in event.camera_ids}) > 1),
        }

    def _derive_risk_level(self, scenario_type: str, confidence: float, features: dict[str, float]) -> str:
        if scenario_type == "CROWD_THREAT":
            return "CRITICAL" if confidence >= 0.60 else "HIGH"
        if scenario_type == "ARMED_INDIVIDUAL":
            return "HIGH" if confidence >= 0.45 else "MEDIUM"
        if scenario_type == "SUSPICIOUS_ACTIVITY":
            return _score_to_risk(max(confidence, features["mean_risk"]))
        return "LOW" if confidence < 0.35 else "MEDIUM"

    def _derive_status(self, cluster: list[Event], scenario_type: str, confidence: float) -> str:
        identity_ids = sorted({identity_id for event in cluster for identity_id in event.identity_ids})
        camera_ids = sorted({camera_id for event in cluster for camera_id in event.camera_ids})
        signature = self._signature(scenario_type, identity_ids, camera_ids)
        previous_risk = self._known_signatures.get(signature)
        current_risk = self._derive_risk_level(scenario_type, confidence, self._cluster_features(cluster))
        if confidence < 0.25 and len(cluster) == 1:
            return SCENARIO_FALSE_ALARM
        if previous_risk and _RISK_ORDER.get(current_risk, 0) > _RISK_ORDER.get(previous_risk, 0):
            return SCENARIO_ESCALATING
        return SCENARIO_ACTIVE

    @staticmethod
    def _signature(scenario_type: str, identity_ids: list[str], camera_ids: list[str]) -> str:
        return "|".join([scenario_type, ",".join(identity_ids), ",".join(camera_ids)])

    def _cluster_vector(self, cluster: list[Event]) -> list[float]:
        vectors = [self._event_vector(event) for event in cluster]
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.size == 0:
            return []
        return matrix.mean(axis=0).astype(float).tolist()

    @staticmethod
    def _summary(scenario_type: str, cluster: list[Event], confidence: float) -> str:
        identities = sorted({identity_id for event in cluster for identity_id in event.identity_ids})
        cameras = sorted({camera_id for event in cluster for camera_id in event.camera_ids})
        return (
            f"{scenario_type} across {len(cluster)} event(s), "
            f"identities={identities or ['unknown']}, cameras={cameras}, confidence={confidence:.2f}"
        )


_WEAPONS = frozenset({"weapon", "pistol", "rifle", "knife", "grenade", "shotgun", "gun", "sword"})
_DEVICES = frozenset({"phone", "tablet", "cell phone"})
_VEHICLES = frozenset({"car", "truck", "bus", "motorcycle"})


class SecurityScenario:
    name = "security"

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [obj.type for obj in result.objects]
        weapons = sorted({label for label in labels if label in _WEAPONS})
        if weapons:
            events.append(
                {
                    "event_type": "WEAPON_DETECTED",
                    "severity": "high",
                    "detail": f"Detected: {', '.join(weapons)}",
                }
            )
        if labels.count("person") > 3:
            events.append(
                {
                    "event_type": "LOITERING_ALERT",
                    "severity": "medium",
                    "detail": f"Multiple persons: {labels.count('person')}",
                }
            )
        return events


class ClassroomScenario:
    name = "classroom"
    MAX_PERSONS = 35

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [obj.type for obj in result.objects]
        count = labels.count("person")
        if count > self.MAX_PERSONS:
            events.append(
                {
                    "event_type": "OVERCROWDING",
                    "severity": "medium",
                    "detail": f"Person count {count} exceeds {self.MAX_PERSONS}",
                }
            )
        devices = sorted({label for label in labels if label in _DEVICES})
        if devices:
            events.append(
                {
                    "event_type": "UNAUTHORIZED_DEVICE",
                    "severity": "low",
                    "detail": f"Devices: {', '.join(devices)}",
                }
            )
        return events


class TrafficScenario:
    name = "traffic"
    PEDESTRIAN_THRESHOLD = 3
    VEHICLE_DENSITY_THRESHOLD = 10

    def evaluate(self, result: DetectionResult) -> list[dict]:
        events: list[dict] = []
        labels = [obj.type for obj in result.objects]
        pedestrians = labels.count("person")
        if pedestrians >= self.PEDESTRIAN_THRESHOLD:
            events.append(
                {
                    "event_type": "PEDESTRIAN_ALERT",
                    "severity": "medium",
                    "detail": f"{pedestrians} pedestrians detected",
                }
            )
        vehicles = sum(1 for label in labels if label in _VEHICLES)
        if vehicles > self.VEHICLE_DENSITY_THRESHOLD:
            events.append(
                {
                    "event_type": "HIGH_TRAFFIC_DENSITY",
                    "severity": "low",
                    "detail": f"Vehicle count: {vehicles}",
                }
            )
        return events


_REGISTRY: dict[str, type] = {
    "security": SecurityScenario,
    "classroom": ClassroomScenario,
    "traffic": TrafficScenario,
}
VALID_SCENARIOS: tuple[str, ...] = tuple(_REGISTRY)


def get_scenario(name: str) -> SecurityScenario | ClassroomScenario | TrafficScenario:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown scenario '{name}'. Valid: {VALID_SCENARIOS}")
    return cls()
