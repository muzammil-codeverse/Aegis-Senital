from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    TRACK_EVENT = "TRACK_EVENT"
    DETECTION_EVENT = "DETECTION_EVENT"
    ANOMALY_EVENT = "ANOMALY_EVENT"
    THREAT_EVENT = "THREAT_EVENT"
    INCIDENT_EVENT = "INCIDENT_EVENT"
    ALERT_EVENT = "ALERT_EVENT"
    SYSTEM_EVENT = "SYSTEM_EVENT"
    FORENSIC_EVENT = "FORENSIC_EVENT"
    HANDOFF_PREDICTED = "HANDOFF_PREDICTED"
    HANDOFF_CONFIRMED = "HANDOFF_CONFIRMED"
    HANDOFF_REJECTED = "HANDOFF_REJECTED"
    HANDOFF_EXPIRED = "HANDOFF_EXPIRED"
    # Phase 20 — identity intelligence
    WATCHLIST_HIT = "watchlist_hit"
    IDENTITY_CANDIDATE_CREATED = "identity_candidate_created"
    # Phase 23 — open-vocabulary threat scanner
    OPEN_VOCAB_SCAN_COMPLETED = "open_vocab_scan_completed"
    OPEN_VOCAB_THREAT_FOUND = "open_vocab_threat_found"
    OPEN_VOCAB_SCAN_FAILED = "open_vocab_scan_failed"
    # Phase 25 — open-vocab streaming integration
    OPEN_VOCAB_SCAN_RESULT = "open_vocab_scan_result"
