from __future__ import annotations

import json
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IdentityNode:
    identity_id: str
    first_seen: float
    last_seen: float
    camera_history: list
    trajectory_history: list
    embedding_history: list
    event_history: list
    risk_history: list
    associated_objects: list
    confidence_history: list


class TemporalIdentityGraph:
    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self._ttl_seconds = float(cfg.get("ttl_seconds", 3600.0))
        self._bucket_seconds = int(cfg.get("time_bucket_seconds", 60))
        self._history_limit = int(cfg.get("history_limit", 200))
        self._snapshot_dir = Path(cfg.get("snapshot_dir", "storage/identity_graph"))
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._nodes: dict[str, IdentityNode] = {}
        self._track_to_identity: dict[tuple[str, int], str] = {}
        self._camera_index: dict[str, set[str]] = defaultdict(set)
        self._time_index: dict[int, set[str]] = defaultdict(set)
        self._last_prune = 0.0
        self._prune_interval = float(cfg.get("prune_interval_seconds", 60.0))

    def update_identity(
        self,
        identity_id: str,
        *,
        camera_id: str | None = None,
        timestamp: float | None = None,
        trajectory: dict | None = None,
        embedding: list[float] | None = None,
        event: dict | None = None,
        risk_score: float | None = None,
        associated_object: dict | None = None,
        confidence: float | None = None,
    ) -> IdentityNode:
        now = timestamp or time.time()
        with self._lock:
            self._maybe_prune(now)
            node = self._nodes.get(identity_id)
            if node is None:
                node = IdentityNode(
                    identity_id=identity_id,
                    first_seen=now,
                    last_seen=now,
                    camera_history=[],
                    trajectory_history=[],
                    embedding_history=[],
                    event_history=[],
                    risk_history=[],
                    associated_objects=[],
                    confidence_history=[],
                )
                self._nodes[identity_id] = node

            node.last_seen = max(node.last_seen, now)
            if camera_id:
                _append_bounded(node.camera_history, {"camera_id": camera_id, "timestamp": now}, self._history_limit)
                self._camera_index[camera_id].add(identity_id)
            if trajectory is not None:
                _append_bounded(node.trajectory_history, {"timestamp": now, **trajectory}, self._history_limit)
            if embedding:
                _append_bounded(node.embedding_history, {"timestamp": now, "embedding": list(embedding)}, self._history_limit)
            if event is not None:
                _append_bounded(node.event_history, {"timestamp": now, **event}, self._history_limit)
            if risk_score is not None:
                _append_bounded(node.risk_history, {"timestamp": now, "risk_score": float(risk_score)}, self._history_limit)
            if associated_object is not None:
                _append_bounded(node.associated_objects, {"timestamp": now, **associated_object}, self._history_limit)
            if confidence is not None:
                _append_bounded(node.confidence_history, {"timestamp": now, "confidence": float(confidence)}, self._history_limit)

            self._time_index[self._bucket(now)].add(identity_id)
            return _copy_node(node)

    def link_track_to_identity(
        self,
        camera_id: str,
        track_id: int,
        identity_id: str,
        *,
        timestamp: float | None = None,
        confidence: float | None = None,
    ) -> IdentityNode:
        with self._lock:
            self._track_to_identity[(camera_id, int(track_id))] = identity_id
        return self.update_identity(
            identity_id,
            camera_id=camera_id,
            timestamp=timestamp,
            confidence=confidence,
        )

    def get_identity(self, identity_id: str) -> IdentityNode | None:
        with self._lock:
            node = self._nodes.get(identity_id)
            return _copy_node(node) if node else None

    def get_candidate_identities(
        self,
        *,
        camera_id: str | None = None,
        timestamp: float | None = None,
        window_seconds: float = 300.0,
        limit: int = 20,
    ) -> list[IdentityNode]:
        with self._lock:
            candidate_ids: set[str] = set()
            if camera_id is not None:
                candidate_ids.update(self._camera_index.get(camera_id, set()))
            if timestamp is not None:
                start = timestamp - window_seconds
                for bucket in range(self._bucket(start), self._bucket(timestamp) + 1):
                    candidate_ids.update(self._time_index.get(bucket, set()))
            if not candidate_ids:
                return []
            nodes = [self._nodes[iid] for iid in candidate_ids if iid in self._nodes]
            nodes.sort(key=lambda node: node.last_seen, reverse=True)
            return [_copy_node(node) for node in nodes[:max(0, limit)]]

    def decay_confidence(self, identity_id: str, now: float | None = None, half_life_seconds: float = 900.0) -> float:
        current = now or time.time()
        with self._lock:
            node = self._nodes.get(identity_id)
            if node is None or not node.confidence_history:
                return 0.0
            latest = float(node.confidence_history[-1].get("confidence", 0.0))
            elapsed = max(0.0, current - float(node.confidence_history[-1].get("timestamp", current)))
            if half_life_seconds <= 0:
                return latest
            return round(latest * math.pow(0.5, elapsed / half_life_seconds), 4)

    def prune_expired(self) -> int:
        with self._lock:
            return self._prune(time.time())

    def snapshot(self) -> str:
        with self._lock:
            path = self._snapshot_dir / f"identity_graph_{int(time.time())}.jsonl"
            nodes = [_copy_node(node) for node in self._nodes.values()]
        with path.open("w", encoding="utf-8") as handle:
            for node in nodes:
                handle.write(json.dumps(asdict(node), sort_keys=True) + "\n")
        return str(path)

    def _bucket(self, timestamp: float) -> int:
        return int(timestamp // max(1, self._bucket_seconds))

    def _maybe_prune(self, now: float) -> None:
        if now - self._last_prune >= self._prune_interval:
            self._prune(now)
            self._last_prune = now

    def _prune(self, now: float) -> int:
        expired = [
            identity_id for identity_id, node in self._nodes.items()
            if now - node.last_seen > self._ttl_seconds
        ]
        if not expired:
            return 0
        expired_set = set(expired)
        for identity_id in expired:
            self._nodes.pop(identity_id, None)
        for index in self._camera_index.values():
            index.difference_update(expired_set)
        for index in self._time_index.values():
            index.difference_update(expired_set)
        self._track_to_identity = {
            key: value for key, value in self._track_to_identity.items()
            if value not in expired_set
        }
        return len(expired)


def _append_bounded(target: list, value: Any, limit: int) -> None:
    target.append(value)
    overflow = len(target) - max(1, limit)
    if overflow > 0:
        del target[:overflow]


def _copy_node(node: IdentityNode) -> IdentityNode:
    return IdentityNode(**json.loads(json.dumps(asdict(node))))
