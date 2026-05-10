from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from inference.identity.runtime_config import load_identity_config

logger = logging.getLogger(__name__)

_DIM = 512
_PURGE_INTERVAL = 60.0
_MAX_HISTORY = 100


def _now_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).isoformat()


class GlobalIdentityRegistry:
    """
    Process-wide cross-camera identity registry.

    Keeps searchable embeddings plus per-identity observation history,
    source-confidence breakdowns, camera visitation state, and audit events
    for merge/split/conflict tracking.
    """

    _instance: "GlobalIdentityRegistry | None" = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "GlobalIdentityRegistry":
        with cls._class_lock:
            if cls._instance is None:
                inst = object.__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        cfg = load_identity_config()
        fusion_cfg = cfg.get("fusion", {})
        reid_cfg = cfg.get("reid", {})
        self._threshold = float(reid_cfg.get("match_threshold", 0.55))
        self._ttl_seconds = float(fusion_cfg.get("identity_ttl_seconds", 600))
        decay_seconds = float(fusion_cfg.get("confidence_decay_seconds", 120))
        self._conf_decay_lambda = math.log(2.0) / max(decay_seconds, 1.0)
        self._lock: threading.RLock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._faiss_index: Any | None = None
        self._faiss_available = False
        self._last_purge = time.monotonic()
        self._try_init_faiss()
        self._initialized = True

    def _try_init_faiss(self) -> None:
        try:
            import faiss

            self._faiss_index = faiss.IndexFlatIP(_DIM)
            self._faiss_available = True
            logger.info("GlobalIdentityRegistry: FAISS IndexFlatIP initialised (dim=%d)", _DIM)
        except ImportError:
            logger.info("GlobalIdentityRegistry: FAISS unavailable - using numpy cosine fallback")

    @staticmethod
    def _normalize(emb: list[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(emb, dtype=np.float32).reshape(-1)
        if arr.size < _DIM:
            arr = np.pad(arr, (0, _DIM - arr.size))
        elif arr.size > _DIM:
            arr = arr[:_DIM]
        norm = float(np.linalg.norm(arr))
        return arr / norm if norm > 0.0 else arr

    def _append_history(self, record: dict[str, Any], confidence: float, timestamp: float) -> None:
        history = record.setdefault("confidence_history", [])
        history.append({"timestamp": timestamp, "confidence": round(float(confidence), 4)})
        if len(history) > _MAX_HISTORY:
            del history[:-_MAX_HISTORY]

    def _append_audit(self, record: dict[str, Any], event_type: str, **payload: Any) -> None:
        events = record.setdefault("audit_events", [])
        events.append({"timestamp": _now_iso(), "type": event_type, **payload})
        if len(events) > _MAX_HISTORY:
            del events[:-_MAX_HISTORY]

    def register_identity(
        self,
        stream_id: str,
        embedding: list[float] | np.ndarray,
        identity_id: str,
        confidence: float = 1.0,
        source_scores: dict[str, float] | None = None,
        source: str = "reid",
    ) -> None:
        if not len(embedding):
            return
        normed = self._normalize(embedding)
        now = time.time()

        with self._lock:
            self._maybe_purge()
            record = self._records.get(identity_id)
            if record is None:
                record = {
                    "global_id": identity_id,
                    "embedding": normed,
                    "confidence": float(confidence),
                    "sources": {"face": 0.0, "reid": 0.0, "track": 0.0},
                    "cameras_seen": set([stream_id]),
                    "camera_observations": {stream_id: 1},
                    "first_seen_ts": now,
                    "last_seen_ts": now,
                    "observation_count": 1,
                    "status": "active",
                    "confidence_history": [],
                    "audit_events": [],
                    "last_stream_id": stream_id,
                }
                self._records[identity_id] = record
                self._append_audit(record, "created", source=source)
            else:
                record["embedding"] = normed
                record["last_seen_ts"] = now
                record["observation_count"] = int(record.get("observation_count", 0)) + 1
                record["cameras_seen"].add(stream_id)
                camera_observations = record.setdefault("camera_observations", {})
                camera_observations[stream_id] = int(camera_observations.get(stream_id, 0)) + 1
                record["status"] = "active"
            record["last_stream_id"] = stream_id
            record["confidence"] = max(float(record.get("confidence", 0.0)), float(confidence))
            if source_scores:
                for key in ("face", "reid", "track"):
                    record["sources"][key] = round(
                        max(float(record["sources"].get(key, 0.0)), float(source_scores.get(key, 0.0))),
                        4,
                    )
                if abs(float(source_scores.get("face", 0.0)) - float(source_scores.get("reid", 0.0))) > 0.45:
                    self.record_conflict(
                        identity_id,
                        reason="face_reid_confidence_disagreement",
                        metadata={"source_scores": source_scores},
                    )
            self._append_history(record, confidence, now)
            self._rebuild_index_locked()

    def record_merge(self, primary_identity_id: str, secondary_identity_id: str, reason: str) -> None:
        with self._lock:
            primary = self._records.get(primary_identity_id)
            secondary = self._records.get(secondary_identity_id)
            if primary is None or secondary is None:
                return
            self._append_audit(primary, "merge", merged_from=secondary_identity_id, reason=reason)
            self._append_audit(secondary, "merged_into", merged_to=primary_identity_id, reason=reason)

    def record_split(self, identity_id: str, reason: str, related_identity_id: str | None = None) -> None:
        with self._lock:
            record = self._records.get(identity_id)
            if record is None:
                return
            self._append_audit(record, "split", reason=reason, related_identity_id=related_identity_id)

    def record_conflict(self, identity_id: str, reason: str, metadata: dict[str, Any] | None = None) -> None:
        with self._lock:
            record = self._records.get(identity_id)
            if record is None:
                return
            self._append_audit(record, "conflict", reason=reason, metadata=metadata or {})
            try:
                from inference.monitoring.metrics import get_metrics

                get_metrics().increment("identity_false_merge_warnings_total")
            except Exception:
                pass

    def _rebuild_index_locked(self) -> None:
        active_vectors = []
        active_ids = []
        for identity_id, record in self._records.items():
            if record.get("status") != "active":
                continue
            vector = record.get("embedding")
            if vector is None:
                continue
            active_vectors.append(vector)
            active_ids.append(identity_id)
        self._active_ids = active_ids
        self._active_matrix = np.stack(active_vectors, axis=0) if active_vectors else None
        if not self._faiss_available:
            return
        import faiss

        self._faiss_index = faiss.IndexFlatIP(_DIM)
        if active_vectors:
            matrix = np.stack(active_vectors, axis=0).astype(np.float32)
            faiss.normalize_L2(matrix)
            self._faiss_index.add(matrix)

    def _maybe_purge(self) -> None:
        now = time.monotonic()
        if now - self._last_purge < _PURGE_INTERVAL:
            return
        self._last_purge = now
        self._purge_expired_locked(time.time())

    def _purge_expired_locked(self, now_ts: float) -> int:
        expired = 0
        for identity_id, record in self._records.items():
            if record.get("status") != "active":
                continue
            if now_ts - float(record.get("last_seen_ts", now_ts)) > self._ttl_seconds:
                record["status"] = "expired"
                self._append_audit(record, "expired")
                expired += 1
        if expired:
            self._rebuild_index_locked()
            try:
                from inference.monitoring.metrics import get_metrics

                get_metrics().record_expired_identity(expired)
            except Exception:
                pass
        return expired

    def _decayed_confidence(self, record: dict[str, Any], now_ts: float) -> float:
        latest = float(record.get("confidence", 0.0))
        last_seen = float(record.get("last_seen_ts", now_ts))
        elapsed = max(0.0, now_ts - last_seen)
        return round(float(latest * math.exp(-self._conf_decay_lambda * elapsed)), 4)

    def search_global(
        self,
        embedding: list[float] | np.ndarray,
        k: int = 5,
        exclude_stream: str | None = None,
    ) -> list[dict[str, Any]]:
        if not len(embedding):
            return []
        normed = self._normalize(embedding)
        now_ts = time.time()

        with self._lock:
            self._maybe_purge()
            if not getattr(self, "_active_ids", []):
                return []
            if self._faiss_available and self._faiss_index is not None and self._faiss_index.ntotal > 0:
                results = self._faiss_search_locked(normed, k, exclude_stream)
            else:
                results = self._numpy_search_locked(normed, k, exclude_stream)
            for hit in results:
                record = self._records.get(hit["identity_id"])
                if record is None:
                    continue
                hit["confidence"] = self._decayed_confidence(record, now_ts)
                hit["sources"] = dict(record.get("sources", {}))
                hit["cameras_seen"] = sorted(record.get("cameras_seen", set()))
                hit["first_seen"] = _now_iso(float(record.get("first_seen_ts", now_ts)))
                hit["last_seen"] = _now_iso(float(record.get("last_seen_ts", now_ts)))
                hit["observation_count"] = int(record.get("observation_count", 0))
                hit["status"] = str(record.get("status", "active"))
            return results

    def _faiss_search_locked(
        self,
        normed: np.ndarray,
        k: int,
        exclude_stream: str | None,
    ) -> list[dict[str, Any]]:
        import faiss

        if not getattr(self, "_active_ids", []):
            return []
        oversample_k = min(k * 3, len(self._active_ids))
        vec = normed.reshape(1, -1).copy()
        faiss.normalize_L2(vec)
        scores, indices = self._faiss_index.search(vec, oversample_k)
        results: list[dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or float(score) < self._threshold:
                continue
            identity_id = self._active_ids[idx]
            record = self._records.get(identity_id)
            if record is None:
                continue
            if exclude_stream and record.get("last_stream_id") == exclude_stream:
                continue
            results.append(
                {
                    "identity_id": identity_id,
                    "global_id": identity_id,
                    "score": round(float(score), 4),
                    "stream_id": record.get("last_stream_id"),
                }
            )
            if len(results) >= k:
                break
        return results

    def _numpy_search_locked(
        self,
        normed: np.ndarray,
        k: int,
        exclude_stream: str | None,
    ) -> list[dict[str, Any]]:
        matrix = getattr(self, "_active_matrix", None)
        if matrix is None:
            return []
        scores = matrix @ normed
        ranked = np.argsort(-scores)
        results: list[dict[str, Any]] = []
        for idx in ranked:
            score = float(scores[idx])
            if score < self._threshold:
                break
            identity_id = self._active_ids[idx]
            record = self._records.get(identity_id)
            if record is None:
                continue
            if exclude_stream and record.get("last_stream_id") == exclude_stream:
                continue
            results.append(
                {
                    "identity_id": identity_id,
                    "global_id": identity_id,
                    "score": round(score, 4),
                    "stream_id": record.get("last_stream_id"),
                }
            )
            if len(results) >= k:
                break
        return results

    def get_identity_record(self, identity_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(identity_id)
            if record is None:
                return None
            now_ts = time.time()
            return {
                "global_id": identity_id,
                "confidence": self._decayed_confidence(record, now_ts),
                "sources": dict(record.get("sources", {})),
                "cameras_seen": sorted(record.get("cameras_seen", set())),
                "first_seen": _now_iso(float(record.get("first_seen_ts", now_ts))),
                "last_seen": _now_iso(float(record.get("last_seen_ts", now_ts))),
                "observation_count": int(record.get("observation_count", 0)),
                "status": str(record.get("status", "active")),
                "camera_observations": dict(record.get("camera_observations", {})),
                "audit_events": list(record.get("audit_events", [])),
            }

    def list_records(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            records = []
            for identity_id in self._records:
                record = self.get_identity_record(identity_id)
                if record is None:
                    continue
                if status and record["status"] != status:
                    continue
                records.append(record)
            records.sort(key=lambda item: item["last_seen"], reverse=True)
            return records[:limit]

    @property
    def total_identities(self) -> int:
        with self._lock:
            return len(self._records)

    def stream_identity_counts(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for record in self._records.values():
                for camera_id in record.get("cameras_seen", set()):
                    counts[camera_id] = counts.get(camera_id, 0) + 1
            return counts

    def force_purge(self) -> int:
        with self._lock:
            return self._purge_expired_locked(time.time())


_registry: GlobalIdentityRegistry = GlobalIdentityRegistry()


def get_global_registry() -> GlobalIdentityRegistry:
    return _registry
