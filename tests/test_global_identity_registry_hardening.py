from __future__ import annotations

import time

from inference.identity.global_identity_registry import get_global_registry


def _reset_registry():
    registry = get_global_registry()
    registry._records.clear()
    registry._active_ids = []
    registry._active_matrix = None
    if hasattr(registry, "_rebuild_index_locked"):
        registry._rebuild_index_locked()
    return registry


def test_identity_ttl_decay_and_expiry():
    registry = _reset_registry()
    registry.register_identity("cam_01", [1.0, 0.0], "gid_001", confidence=0.9, source_scores={"reid": 0.9})
    record = registry._records["gid_001"]
    record["last_seen_ts"] = time.time() - registry._ttl_seconds - 5
    purged = registry.force_purge()
    assert purged == 1
    assert registry.get_identity_record("gid_001")["status"] == "expired"


def test_identity_conflict_event_created():
    registry = _reset_registry()
    registry.register_identity(
        "cam_01",
        [1.0, 0.0],
        "gid_002",
        confidence=0.8,
        source_scores={"face": 0.95, "reid": 0.10, "track": 0.7},
    )
    record = registry.get_identity_record("gid_002")
    event_types = [event["type"] for event in record["audit_events"]]
    assert "conflict" in event_types
