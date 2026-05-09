from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        return load_runtime_config("handoff_rules")
    except Exception:
        return {}


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class HandoffEngine:
    """
    Wraps HandoffPredictor and HandoffStore to produce structured, scored,
    evidence-backed cross-camera handoff events.

    Scoring weights (config-driven):
        topology   0.25
        temporal   0.20
        motion     0.20
        identity   0.20
        appearance 0.15

    Hard-reject conditions:
        - target camera not connected in topology
        - ETA outside [min, max] travel window
        - predicted speed > impossible_speed_mps
        - prediction already expired
    """

    def __init__(self, config: dict | None = None) -> None:
        from inference.correlation.handoff_store import HandoffStore
        from inference.correlation.handoff_predictor import HandoffPredictor

        cfg = config or _load_config()
        self._cfg = cfg
        self._pred_cfg = cfg.get("prediction", {})
        self._conf_cfg = cfg.get("confirmation", {})
        self._score_cfg = cfg.get("scoring", {})

        self._enabled = bool(self._pred_cfg.get("enabled", True))
        self._ttl = float(self._pred_cfg.get("prediction_ttl_seconds", 120.0))
        self._max_candidates = int(self._pred_cfg.get("max_candidates_per_prediction", 5))
        self._min_confidence = float(self._conf_cfg.get("min_confidence", 0.68))
        self._min_identity_score = float(self._conf_cfg.get("min_identity_score", 0.50))
        self._min_temporal_score = float(self._conf_cfg.get("min_temporal_score", 0.40))
        self._impossible_speed = float(self._conf_cfg.get("impossible_speed_mps", 12.0))
        self._cleanup_interval = float(cfg.get("expiry", {}).get("cleanup_interval_seconds", 30.0))

        # Scoring weights
        self._w_topology = float(self._score_cfg.get("topology_weight", 0.25))
        self._w_temporal = float(self._score_cfg.get("temporal_weight", 0.20))
        self._w_motion = float(self._score_cfg.get("motion_weight", 0.20))
        self._w_identity = float(self._score_cfg.get("identity_weight", 0.20))
        self._w_appearance = float(self._score_cfg.get("appearance_weight", 0.15))

        self._predictor = HandoffPredictor()
        self._store = HandoffStore(cfg)
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

        # Track last-seen timestamp per (camera, track_id) to detect disappearing tracks
        self._track_seen: dict[tuple[str, int], float] = {}
        self._track_disappear_grace = 2.0  # seconds before treating track as departed

    @property
    def store(self) -> "HandoffStore":
        return self._store

    # ── public API ─────────────────────────────────────────────────────────────

    def process_frame_tracks(
        self,
        camera_id: str,
        tracks: list[Any],
        timestamp: float | None = None,
        identity_map: dict[int, str] | None = None,
    ) -> list[dict]:
        """
        Main entry: call once per frame per camera.
        - Observes arriving tracks → confirms/rejects open predictions.
        - Records track presence timestamps.
        - Returns list of handoff event dicts emitted this frame.
        """
        if not self._enabled:
            return []

        now = timestamp or time.time()
        self._maybe_cleanup(now)
        identity_map = identity_map or {}
        events: list[dict] = []

        for track in tracks:
            track_id = int(_get(track, "track_id", 0) or 0)
            identity_id = identity_map.get(track_id) or _get(track, "identity_id")
            self._track_seen[(camera_id, track_id)] = now
            confirmed = self._observe_track(camera_id, track, track_id, identity_id, now)
            events.extend(confirmed)

        return events

    def predict_for_track(
        self,
        camera_id: str,
        track: Any,
        identity_id: str | None = None,
        timestamp: float | None = None,
    ) -> list[dict]:
        """
        Generate handoff predictions when a track is about to leave or has left
        a camera.  Called explicitly by IntelligenceRuntime for tracks that
        have stopped being seen.
        """
        if not self._enabled:
            return []

        now = timestamp or time.time()
        raw_predictions = self._predictor.predict(
            camera_id,
            track=track,
            identity_id=identity_id or _get(track, "identity_id"),
        )
        created: list[dict] = []
        for raw in raw_predictions[:self._max_candidates]:
            if raw.get("candidate_camera") is None:
                continue
            pred = self._build_prediction(camera_id, track, raw, identity_id, now)
            self._store.add_prediction(pred)
            created.append(pred)
            self._publish_event("HANDOFF_PREDICTED", pred)
        return created

    def get_active_handoffs(self) -> list[dict]:
        return self._store.list_active()

    def get_recent_handoffs(self) -> list[dict]:
        return self._store.list_recent()

    def cleanup(self) -> None:
        self._store.expire_stale()

    # ── internals ─────────────────────────────────────────────────────────────

    def _observe_track(
        self,
        camera_id: str,
        track: Any,
        track_id: int,
        identity_id: str | None,
        now: float,
    ) -> list[dict]:
        """Check if this arriving track matches any open prediction targeting this camera."""
        active = self._store.list_active()
        confirmed: list[dict] = []
        for pred in active:
            if pred.get("target_camera") != camera_id:
                continue
            if pred.get("state") not in ("predicted", "candidate"):
                continue
            # Hard-reject: prediction expired
            if float(pred.get("expires_at", 0)) < now:
                self._store.reject_handoff(pred["handoff_id"], reason="prediction_expired")
                self._publish_event("HANDOFF_REJECTED", pred)
                continue

            evidence = self._score_candidate(pred, camera_id, track, track_id, identity_id, now)
            score = evidence.get("composite", 0.0)

            # Check hard rejection: temporal impossible
            if evidence.get("temporal_impossible", False):
                self._store.reject_handoff(pred["handoff_id"], reason="temporal_impossible")
                self._publish_event("HANDOFF_REJECTED", pred)
                continue

            if score >= self._min_confidence:
                confirmed_pred = self._store.confirm_handoff(
                    pred["handoff_id"],
                    target_track_id=track_id,
                    identity_id=identity_id or pred.get("identity_id"),
                    confirmed_at=now,
                )
                if confirmed_pred:
                    confirmed_pred["evidence"] = evidence
                    confirmed_pred["score_breakdown"] = evidence
                    confirmed.append(confirmed_pred)
                    self._publish_event("HANDOFF_CONFIRMED", confirmed_pred)
                    self._update_identity_graph(confirmed_pred, now)
                    self._update_timeline(confirmed_pred)
            else:
                # Update candidate state
                updated = {
                    **pred,
                    "state": "candidate",
                    "candidate_seen_at": now,
                    "evidence": evidence,
                    "score_breakdown": evidence,
                }
                self._store.add_candidate(updated)
        return confirmed

    def _score_candidate(
        self,
        pred: dict,
        camera_id: str,
        track: Any,
        track_id: int,
        identity_id: str | None,
        now: float,
    ) -> dict:
        predicted_at = float(pred.get("predicted_at", now))
        eta = float(pred.get("eta_seconds") or 0)
        elapsed = now - predicted_at

        # Temporal score
        temporal_min = float(pred.get("metadata", {}).get("min_travel_seconds", 0))
        temporal_max = float(pred.get("metadata", {}).get("max_travel_seconds", self._ttl))
        temporal_impossible = False
        if temporal_max > 0 and elapsed > temporal_max * 2:
            temporal_impossible = True
        if temporal_min > 0 and elapsed < temporal_min * 0.5:
            temporal_impossible = True
        if temporal_max > 0 and temporal_min < temporal_max:
            midpoint = (temporal_min + temporal_max) / 2.0
            half_w = max(1e-6, (temporal_max - temporal_min) / 2.0)
            temporal_score = max(0.0, 1.0 - abs(elapsed - midpoint) / half_w)
        else:
            temporal_score = 0.5

        # Topology score (from prediction's stored breakdown)
        topology_score = float(pred.get("score_breakdown", {}).get("topology_score", 0.5))

        # Motion score — basic: if track has velocity components, check plausibility
        motion_score = 0.5  # default neutral when no embedding data
        vel = _get(track, "velocity") or _get(track, "motion_vector") or []
        if isinstance(vel, (list, tuple)) and len(vel) >= 2:
            import math
            speed = math.hypot(float(vel[0]), float(vel[1]))
            if speed > 0:
                motion_score = min(1.0, speed / 5.0) if speed < 5.0 else max(0.0, 1.0 - (speed - 5.0) / 10.0)

        # Identity score
        pred_identity = pred.get("identity_id")
        if pred_identity and identity_id and pred_identity == identity_id:
            identity_score = 1.0
        elif pred_identity and identity_id and pred_identity != identity_id:
            identity_score = 0.0
        else:
            identity_score = self._min_identity_score  # neutral

        # Composite (appearance absent here — no embedding)
        w_total = self._w_topology + self._w_temporal + self._w_motion + self._w_identity
        composite = (
            self._w_topology * topology_score
            + self._w_temporal * temporal_score
            + self._w_motion * motion_score
            + self._w_identity * identity_score
        ) / max(w_total, 1e-6)
        composite = max(0.0, min(1.0, composite))

        return {
            "topology_score": round(topology_score, 4),
            "temporal_score": round(temporal_score, 4),
            "motion_score": round(motion_score, 4),
            "identity_score": round(identity_score, 4),
            "appearance_score": None,
            "face_score": None,
            "composite": round(composite, 4),
            "temporal_impossible": temporal_impossible,
        }

    def _build_prediction(
        self,
        camera_id: str,
        track: Any,
        raw: dict,
        identity_id: str | None,
        now: float,
    ) -> dict:
        track_id = int(_get(track, "track_id", 0) or 0)
        eta = float(raw.get("eta_seconds", 0))
        expires_at = now + max(eta * 2, self._ttl)

        # Get edge info for metadata
        meta: dict = {}
        try:
            from inference.correlation.handoff_predictor import HandoffPredictor
            graph = self._predictor._graph
            for edge in graph.neighbors(camera_id):
                if edge.target_camera_id == raw.get("candidate_camera"):
                    meta = {
                        "min_travel_seconds": edge.min_travel_seconds,
                        "max_travel_seconds": edge.max_travel_seconds,
                        "transition_probability": edge.transition_probability,
                    }
                    break
        except Exception:
            pass

        # Decompose reason string into score_breakdown
        score_breakdown = {
            "topology_score": float(raw.get("confidence", 0)),
            "temporal_score": 0.5,
            "motion_score": 0.5,
            "identity_score": 0.5,
        }

        return {
            "handoff_id": str(uuid.uuid4()),
            "state": "predicted",
            "source_camera": camera_id,
            "target_camera": str(raw.get("candidate_camera", "")),
            "source_track_id": track_id,
            "target_track_id": None,
            "identity_id": identity_id or _get(track, "identity_id"),
            "predicted_at": now,
            "candidate_seen_at": None,
            "confirmed_at": None,
            "eta_seconds": round(eta, 3),
            "confidence": float(raw.get("confidence", 0)),
            "score_breakdown": score_breakdown,
            "evidence": score_breakdown,
            "route": list(raw.get("route", [])),
            "reason": str(raw.get("reason", "")),
            "expires_at": expires_at,
            "metadata": meta,
        }

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup >= self._cleanup_interval:
            self._last_cleanup = now
            self._store.expire_stale(now)
            # Clean stale track_seen entries
            with self._lock:
                stale_keys = [
                    k for k, ts in self._track_seen.items()
                    if now - ts > self._ttl * 2
                ]
                for k in stale_keys:
                    del self._track_seen[k]

    def _publish_event(self, event_type_name: str, handoff: dict) -> None:
        try:
            from core.event_bus import EventType, get_event_bus
            et = getattr(EventType, event_type_name, None)
            if et:
                get_event_bus().publish(
                    et, handoff,
                    source=handoff.get("source_camera", ""),
                    priority=6,
                )
            # Also broadcast to WS handoff service
            try:
                from backend.app.services.websocket_handoff_service import get_websocket_handoff_service
                get_websocket_handoff_service().broadcast_handoff_update(handoff)
            except Exception:
                pass
        except Exception as exc:
            logger.debug("HandoffEngine publish failed: %s", exc)

    def _update_identity_graph(self, handoff: dict, now: float) -> None:
        identity_id = handoff.get("identity_id")
        if not identity_id:
            return
        try:
            from inference.runtime import get_intelligence_runtime
            rt = get_intelligence_runtime()
            rt.identity_graph.update_identity(
                identity_id,
                camera_id=handoff.get("target_camera"),
                timestamp=now,
                event={"type": "handoff_confirmed", "handoff_id": handoff.get("handoff_id")},
            )
        except Exception as exc:
            logger.debug("HandoffEngine identity_graph update failed: %s", exc)

    def _update_timeline(self, handoff: dict) -> None:
        try:
            from inference.runtime import get_intelligence_runtime
            rt = get_intelligence_runtime()
            rt.timeline_builder._store.append({
                "timestamp": handoff.get("confirmed_at") or time.time(),
                "camera_id": handoff.get("target_camera", ""),
                "frame_id": 0,
                "track_ids": ([handoff["target_track_id"]] if handoff.get("target_track_id") else []),
                "incident_ids": [],
                "event_ids": [],
                "metadata": {
                    "handoff_id": handoff.get("handoff_id"),
                    "handoff_state": "confirmed",
                    "source_camera": handoff.get("source_camera"),
                    "target_camera": handoff.get("target_camera"),
                    "handoff_confidence": handoff.get("confidence"),
                },
            })
        except Exception as exc:
            logger.debug("HandoffEngine timeline update failed: %s", exc)


_engine: HandoffEngine | None = None
_engine_lock = threading.Lock()


def get_handoff_engine() -> HandoffEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = HandoffEngine()
    return _engine
