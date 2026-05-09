from __future__ import annotations

import threading
import time
import logging
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from core.event_bus import EventType, get_event_bus
from core.runtime import get_runtime_supervisor
from inference.alerts.alert_manager import AlertManager
from inference.alerts.alert_router import AlertRouter
from inference.alerts.alert_store import AlertStore
from inference.alerts.notification.dispatcher import NotificationDispatcher
from inference.anomaly.anomaly_engine import AnomalyEngine
from inference.config_runtime import load_runtime_config
from inference.correlation.handoff_predictor import HandoffPredictor
from inference.forensics.replay_indexer import ReplayIndexer
from inference.forensics.timeline_builder import TimelineBuilder
from inference.identity.temporal_identity_graph import TemporalIdentityGraph
from inference.reasoning.incident_engine import IncidentEngine
from inference.trajectory.trajectory_engine import TrajectoryEngine

logger = logging.getLogger(__name__)


class IntelligenceRuntime:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _safe_runtime_config()
        self._lock = threading.RLock()
        self.trajectory_engine = TrajectoryEngine()
        self.anomaly_engine = AnomalyEngine()
        self.incident_engine = IncidentEngine()
        self.handoff_predictor = HandoffPredictor()
        self.timeline_builder = TimelineBuilder()
        self.replay_indexer = ReplayIndexer()
        self.alert_store = AlertStore()
        self.alert_router = AlertRouter()
        self.alert_manager = AlertManager(store=self.alert_store, router=self.alert_router)
        self.notification_dispatcher = NotificationDispatcher(router=self.alert_router)
        self.identity_graph = TemporalIdentityGraph(cfg.get("identity_graph", {}))
        self.context_engine = _optional_context_engine()
        self._packet_history = deque(maxlen=int(cfg.get("packet_history_size", 1_000)))
        self._track_timelines: dict[str, deque[dict]] = defaultdict(
            lambda: deque(maxlen=int(cfg.get("track_timeline_size", 500)))
        )
        self._heatmap_points: dict[str, deque[dict]] = defaultdict(
            lambda: deque(maxlen=int(cfg.get("heatmap_points", 2_000)))
        )
        self._heatmap_ttl = float(cfg.get("heatmap_ttl_seconds", 600.0))
        self._heatmap_grid = list(cfg.get("heatmap_grid_size", [16, 9]))
        self._last_cleanup = 0.0
        self._cleanup_interval = float(cfg.get("cleanup_interval_seconds", 30.0))
        self._metrics = {
            "frames": 0,
            "trajectories": 0,
            "anomalies": 0,
            "incidents": 0,
            "alerts": 0,
            "handoff_predictions": 0,
        }

    def process_frame_context(
        self,
        camera_id: str,
        frame_id: int,
        timestamp: float | str,
        tracks: list[Any] | None,
        events: list[Any] | None,
        detections: list[Any] | None = None,
        trajectories: list[dict] | None = None,
        anomalies: list[dict] | None = None,
    ) -> dict:
        ts = _timestamp_float(timestamp)
        tracks = list(tracks or [])
        events = list(events or [])
        detections = list(detections or [])
        with self._lock:
            self._cleanup_if_needed(ts)

            if trajectories is None:
                trajectories = [
                    self.trajectory_engine.update(track, timestamp=ts)
                    for track in tracks
                    if int(_get(track, "missed_frames", 0) or 0) == 0
                ]
            if anomalies is None:
                anomalies = self.anomaly_engine.evaluate_trajectories(
                    trajectories,
                    camera_id=camera_id,
                    frame_id=frame_id,
                    timestamp=ts,
                )
            handoffs = [
                prediction
                for track in tracks
                for prediction in self.handoff_predictor.predict(
                    camera_id,
                    track=track,
                    identity_id=_get(track, "identity_id"),
                )
                if prediction.get("candidate_camera") is not None
            ]
            self._update_identity_graph(camera_id, ts, tracks, trajectories, events, anomalies)
            incidents = self.incident_engine.process(events=events, anomalies=anomalies, timeline_ref=None)
            alerts = self._process_alerts(incidents, events)
            timeline_record = self.timeline_builder.record_frame(
                timestamp=ts,
                camera_id=camera_id,
                frame_id=frame_id,
                tracks=tracks,
                events=events,
                incidents=incidents,
                anomalies=anomalies,
                metadata={"handoffs": handoffs, "alert_ids": [alert["alert_id"] for alert in alerts]},
            )
            replay_path = self.replay_indexer.append(timeline_record)
            self.incident_engine.attach_timeline_ref(
                [incident["incident_id"] for incident in incidents],
                timeline_record,
            )
            timeline_record["metadata"]["replay_index_path"] = replay_path
            packet = {
                "frame_id": int(frame_id),
                "camera_id": camera_id,
                "timestamp": ts,
                "detections": [_to_dict(item) for item in detections],
                "tracks": [_to_dict(item) for item in tracks],
                "trajectories": trajectories,
                "anomalies": anomalies,
                "events": [_to_dict(item) for item in events],
                "incidents": incidents,
                "alerts": alerts,
                "metrics": {
                    "runtime": dict(self._metrics),
                    "trajectory": self.trajectory_engine.get_metrics(),
                    "anomaly": self.anomaly_engine.get_metrics(),
                    "incident": self.incident_engine.get_metrics(),
                    "alert": {
                        "active_alerts": len(self.alert_manager.list_alerts(limit=2_000)),
                        "new_alerts": len(alerts),
                    },
                    "handoff_predictions": len(handoffs),
                },
            }
            packet["metrics"]["forensics"] = {
                "timeline_path": timeline_record.get("metadata", {}).get("timeline_path"),
                "replay_index_path": replay_path,
            }
            packet["metrics"]["handoffs"] = handoffs
            self._record_packet(packet, tracks, trajectories, events, anomalies, incidents, timeline_record)

        bus = get_event_bus()
        if detections:
            bus.publish(EventType.DETECTION_EVENT, packet, source=camera_id, priority=5)
        if tracks:
            bus.publish(EventType.TRACK_EVENT, packet, source=camera_id, priority=5)
        bus.publish(EventType.FORENSIC_EVENT, timeline_record, source=camera_id, priority=7)
        supervisor = get_runtime_supervisor()
        supervisor.update_metric("intelligence_frames", self._metrics["frames"])
        supervisor.report_stream_stall(camera_id, ts)
        supervisor.evaluate_health()
        # Mark event seen on camera registry if events or incidents occurred
        if events or packet.get("incidents"):
            try:
                from app.services.camera_registry import get_camera_registry
                get_camera_registry().mark_event_seen(camera_id, timestamp=ts)
            except Exception:
                pass
        return packet

    def get_incidents(self) -> list[dict]:
        return self.incident_engine.get_incidents()

    def get_track_timeline(self, track_id: int | str) -> list[dict]:
        key = str(track_id)
        with self._lock:
            memory = list(self._track_timelines.get(key, []))
        persisted = self.timeline_builder.get_track_timeline(track_id)
        combined = memory + [item for item in persisted if item not in memory]
        combined.sort(key=lambda item: item.get("timestamp", 0.0))
        return combined

    def get_live_anomalies(self) -> list[dict]:
        return self.anomaly_engine.get_live_anomalies()

    def get_camera_heatmap(self, camera_id: str) -> dict:
        now = time.time()
        grid_x = int(self._heatmap_grid[0]) if self._heatmap_grid else 16
        grid_y = int(self._heatmap_grid[1]) if len(self._heatmap_grid) > 1 else 9
        cells: dict[tuple[int, int], float] = defaultdict(float)
        with self._lock:
            points = [
                point for point in self._heatmap_points.get(camera_id, [])
                if now - float(point.get("timestamp", now)) <= self._heatmap_ttl
            ]
        for point in points:
            x = min(grid_x - 1, max(0, int(point["x"] * grid_x)))
            y = min(grid_y - 1, max(0, int(point["y"] * grid_y)))
            cells[(x, y)] += 1.0
        max_density = max(cells.values(), default=0.0)
        return {
            "camera_id": camera_id,
            "grid_size": [grid_x, grid_y],
            "cells": [
                {"x": x, "y": y, "density": density}
                for (x, y), density in sorted(cells.items())
            ],
            "max_density": max_density,
            "generated_at": now,
        }

    def get_health(self) -> dict:
        return {
            "status": "ok",
            "metrics": dict(self._metrics),
            "event_bus": get_event_bus().health(),
            "supervisor": get_runtime_supervisor().get_health_snapshot(),
        }

    def get_alerts(
        self,
        state: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> dict:
        alerts = [alert.to_dict() for alert in self.alert_manager.list_alerts(state=state, severity=severity, limit=limit)]
        return {"items": alerts, "count": len(alerts), "status": "ok" if alerts else "empty"}

    def get_alert(self, alert_id: str) -> dict:
        alert = self.alert_manager.get_alert(alert_id)
        return {"item": alert.to_dict() if alert else None, "status": "ok" if alert else "not_found"}

    def acknowledge_alert(self, alert_id: str, operator_id: str | None = None) -> dict:
        alert = self.alert_manager.acknowledge_alert(alert_id, operator_id=operator_id)
        return {"item": alert.to_dict() if alert else None, "status": "ok" if alert else "not_found"}

    def resolve_alert(self, alert_id: str, operator_id: str | None = None) -> dict:
        alert = self.alert_manager.resolve_alert(alert_id, operator_id=operator_id)
        return {"item": alert.to_dict() if alert else None, "status": "ok" if alert else "not_found"}

    def escalate_alert(self, alert_id: str, reason: str | None = None) -> dict:
        alert = self.alert_manager.escalate_alert(alert_id, reason=reason)
        return {"item": alert.to_dict() if alert else None, "status": "ok" if alert else "not_found"}

    def get_live_alert_feed(self, limit: int = 100) -> dict:
        items = self.alert_manager.get_live_alert_feed(limit=limit)
        return {"items": items, "count": len(items), "status": "ok" if items else "empty"}

    def get_alert_history(self, alert_id: str) -> dict:
        history = self.alert_manager.get_alert_history(alert_id)
        return {"items": history, "count": len(history), "status": "ok" if history else "empty"}

    def cleanup(self) -> None:
        with self._lock:
            self.trajectory_engine.cleanup()
            self.anomaly_engine.cleanup()
            self.incident_engine.cleanup()
            self.alert_manager.expire_stale_alerts()
            self.identity_graph.prune_expired()
            self._cleanup_heatmap_locked(time.time())

    def _process_alerts(self, incidents: list[dict], events: list[Any]) -> list[dict]:
        alerts = []
        incident_alert_created = False
        for incident in incidents:
            alert = self.alert_manager.create_alert_from_incident(incident)
            if alert is None:
                continue
            incident_alert_created = True
            if alert.state.value != "suppressed":
                self._dispatch_alert(alert)
            alerts.append(alert.to_dict())

        if not incident_alert_created:
            for event in events:
                alert = self.alert_manager.create_alert_from_event(event)
                if alert is None:
                    continue
                if alert.state.value != "suppressed":
                    self._dispatch_alert(alert)
                alerts.append(alert.to_dict())
        return alerts

    def _dispatch_alert(self, alert: Any) -> None:
        results = self.notification_dispatcher.dispatch(alert)
        for result in results:
            self.alert_manager.record_dispatch_attempt(alert.alert_id, str(result.get("channel", "unknown")), result)
        self.alert_manager.mark_dispatched(alert.alert_id, {"dispatch_results": results})

    def _record_packet(
        self,
        packet: dict,
        tracks: list[Any],
        trajectories: list[dict],
        events: list[Any],
        anomalies: list[dict],
        incidents: list[dict],
        timeline_record: dict,
    ) -> None:
        self._packet_history.append(packet)
        self._metrics["frames"] += 1
        self._metrics["trajectories"] += len(trajectories)
        self._metrics["anomalies"] += len(anomalies)
        self._metrics["incidents"] += len(incidents)
        self._metrics["alerts"] += len(packet.get("alerts", []))
        self._metrics["handoff_predictions"] += int(packet["metrics"].get("handoff_predictions", 0))
        for track in tracks:
            track_id = _get(track, "track_id")
            if track_id is None:
                continue
            self._track_timelines[str(track_id)].append(timeline_record)
            bbox = list(_get(track, "bbox", []) or [])
            if len(bbox) == 4:
                cx = ((float(bbox[0]) + float(bbox[2])) / 2.0) / 640.0
                cy = ((float(bbox[1]) + float(bbox[3])) / 2.0) / 640.0
                self._heatmap_points[_get(track, "camera_id") or packet["camera_id"]].append(
                    {"x": max(0.0, min(1.0, cx)), "y": max(0.0, min(1.0, cy)), "timestamp": packet["timestamp"]}
                )

    def _update_identity_graph(
        self,
        camera_id: str,
        timestamp: float,
        tracks: list[Any],
        trajectories: list[dict],
        events: list[Any],
        anomalies: list[dict],
    ) -> None:
        trajectory_by_track = {item["track_id"]: item for item in trajectories}
        for track in tracks:
            identity_id = _get(track, "identity_id")
            track_id = _get(track, "track_id")
            if not identity_id or track_id is None:
                continue
            trajectory = trajectory_by_track.get(track_id)
            self.identity_graph.link_track_to_identity(
                camera_id,
                int(track_id),
                str(identity_id),
                timestamp=timestamp,
                confidence=float(_get(track, "identity_confidence", 0.0) or 0.0),
            )
            embedding = _get(track, "appearance_embedding") or _get(track, "face_embedding")
            self.identity_graph.update_identity(
                str(identity_id),
                camera_id=camera_id,
                timestamp=timestamp,
                trajectory=trajectory,
                embedding=embedding,
                risk_score=max([float(_get(event, "risk_score", 0.0) or 0.0) for event in events], default=0.0),
                confidence=float(_get(track, "identity_confidence", 0.0) or 0.0),
            )
        for event in events:
            for identity_id in _get(event, "identity_ids", []) or []:
                self.identity_graph.update_identity(
                    str(identity_id),
                    camera_id=camera_id,
                    timestamp=timestamp,
                    event=_to_dict(event),
                    risk_score=float(_get(event, "risk_score", 0.0) or 0.0),
                )

    def _cleanup_if_needed(self, now: float) -> None:
        if now - self._last_cleanup >= self._cleanup_interval:
            self.cleanup()
            self._last_cleanup = now

    def _cleanup_heatmap_locked(self, now: float) -> None:
        for camera_id, points in list(self._heatmap_points.items()):
            kept = [point for point in points if now - float(point.get("timestamp", now)) <= self._heatmap_ttl]
            self._heatmap_points[camera_id] = deque(kept, maxlen=points.maxlen)


def _safe_runtime_config() -> dict:
    cfg: dict = {}
    for name in ("forensics", "runtime_health"):
        try:
            cfg[name] = load_runtime_config(name)
        except FileNotFoundError:
            cfg[name] = {}
    runtime = cfg.get("forensics", {}).get("runtime", {})
    return runtime if isinstance(runtime, dict) else {}


def _optional_context_engine() -> Any | None:
    try:
        from inference.context.context_engine import ContextEngine
        return ContextEngine()
    except Exception as exc:
        logger.info("ContextEngine unavailable for IntelligenceRuntime: %s", exc)
        return None


def _timestamp_float(value: float | str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return time.time()


def _to_dict(item: Any) -> dict:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, dict):
        return dict(item)
    return {"value": item}


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


_runtime: IntelligenceRuntime | None = None
_runtime_lock = threading.Lock()


def get_intelligence_runtime(config: dict | None = None) -> IntelligenceRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = IntelligenceRuntime(config)
    return _runtime
