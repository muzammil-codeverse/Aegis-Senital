from __future__ import annotations

import threading


class SystemMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.frames_processed = 0
        self.frames_dropped = 0
        self.queue_overflows = 0
        self.avg_latency_ms = 0
        self.max_latency_ms = 0
        self.circuit_breaker_trips = 0
        self.id_switches = 0
        self.alerts_created = 0
        self.alerts_dispatched = 0
        self.alerts_acknowledged = 0
        self.alerts_resolved = 0
        self.alerts_escalated = 0
        self.alerts_suppressed = 0
        self.notification_failures = 0
        self.websocket_clients = 0
        self.websocket_dropped_messages = 0
        # Phase 15-16: camera registry and streaming metrics
        self.registered_cameras = 0
        self.active_streams = 0
        self.offline_cameras = 0
        self.degraded_cameras = 0
        self.stream_start_failures = 0
        self.latest_frame_updates = 0
        self.active_mjpeg_clients = 0
        self.mjpeg_frames_served = 0
        self.mjpeg_client_disconnects = 0
        self.stale_camera_frames = 0
        # Phase 17: forensic console and annotated replay metrics
        self.annotated_frames_generated = 0
        self.annotation_failures = 0
        self.websocket_frame_clients = 0
        self.websocket_frame_messages = 0
        self.websocket_frame_dropped_messages = 0
        self.camera_timeline_queries = 0
        self.incident_replay_queries = 0
        # Phase 18: geospatial operations map metrics
        self.map_state_requests = 0
        self.map_zone_queries = 0
        self.map_topology_queries = 0
        self.geofence_checks = 0
        self.map_incident_markers = 0
        self.map_alert_markers = 0
        # Phase 19: cross-camera handoff metrics
        self.handoff_predictions_created = 0
        self.handoff_candidates_observed = 0
        self.handoffs_confirmed = 0
        self.handoffs_rejected = 0
        self.handoffs_expired = 0
        self.active_handoffs = 0
        self.websocket_handoff_clients = 0
        self.websocket_handoff_messages = 0
        self.websocket_handoff_dropped_messages = 0
        # Phase 21: security, RBAC, audit, and privacy controls
        self.auth_logins_success = 0
        self.auth_logins_failed = 0
        self.auth_access_denied = 0
        self.audit_events_written = 0
        self.audit_write_failures = 0
        self.users_active = 0
        self.users_locked = 0
        self.watchlist_sensitive_reads = 0
        self.forensic_sensitive_reads = 0
        # Phase 22: security hardening completion
        self.auth_rate_limited = 0
        self.websocket_auth_success = 0
        self.websocket_auth_failed = 0
        self.password_changes = 0
        self.password_reset_by_admin = 0
        self.audit_integrity_checks = 0
        self.audit_integrity_failures = 0
        self.object_authz_denied = 0
        self.mfa_challenges_created = 0
        self.mfa_challenges_failed = 0

    def increment(self, counter: str, n: int = 1):
        if n < 0:
            raise ValueError("metrics increments must be non-negative")
        with self._lock:
            setattr(self, counter, max(0, getattr(self, counter, 0) + n))

    def set_value(self, counter: str, value: int | float):
        with self._lock:
            setattr(self, counter, max(0, value))

    def to_dict(self):
        with self._lock:
            return {
                key: value
                for key, value in self.__dict__.items()
                if not key.startswith("_")
            }
