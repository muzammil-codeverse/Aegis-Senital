from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_DIM = 512
_CROSS_STREAM_THRESHOLD = 0.72   # min cosine similarity to count as a cross-stream match
_TTL_SECONDS = 600.0             # 10 minutes — identities unseen longer than this are purged
_CONF_DECAY_LAMBDA = 0.00005     # exponential decay; halves in ~14400 s (~4 hours)
_PURGE_INTERVAL = 60.0           # lazy-purge check at most once per minute


class GlobalIdentityRegistry:
    """
    Process-wide singleton identity index shared across all stream processors.

    Enables cross-stream person re-identification: when stream A registers a
    person identity, stream B can retrieve the same identity_id for the same
    person even if the two cameras have no temporal overlap.

    Phase-6 additions:
        - Per-identity TTL (10 min since last_seen) with lazy purge
        - Confidence decay over time (exponential, very slow)
        - Decayed confidence exposed in search results

    Backend selection (in order of preference):
        1. FAISS IndexFlatIP  — O(N) exact inner-product search on normalized vectors
        2. NumPy fallback     — cosine dot-product scan; no dependency required

    Both backends return the same results for normalized embeddings.

    Usage:
        reg = get_global_registry()
        reg.register_identity("cam_01", appearance_embedding, identity_id)
        hits = reg.search_global(embedding, exclude_stream="cam_01", k=5)
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
        self._lock: threading.RLock = threading.RLock()
        self._embeddings: list[np.ndarray] = []   # normalized (512,) vectors
        self._identity_ids: list[str] = []
        self._stream_ids: list[str] = []
        self._faiss_index: Any | None = None
        self._faiss_available: bool = False
        # Phase 6 — per-identity lifecycle metadata
        self._created_at: dict[str, float] = {}    # identity_id -> monotonic timestamp
        self._last_seen: dict[str, float] = {}     # identity_id -> monotonic timestamp
        self._confidence: dict[str, float] = {}    # identity_id -> initial confidence
        self._last_purge: float = time.monotonic()
        self._try_init_faiss()
        self._initialized: bool = True

    # ── backend init ──────────────────────────────────────────────────────────

    def _try_init_faiss(self) -> None:
        try:
            import faiss
            self._faiss_index = faiss.IndexFlatIP(_DIM)
            self._faiss_available = True
            logger.info("GlobalIdentityRegistry: FAISS IndexFlatIP initialised (dim=%d)", _DIM)
        except ImportError:
            logger.info("GlobalIdentityRegistry: FAISS not installed — using numpy cosine fallback")

    # ── normalisation ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(emb: list[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(emb, dtype=np.float32).reshape(-1)
        if arr.size < _DIM:
            arr = np.pad(arr, (0, _DIM - arr.size))
        elif arr.size > _DIM:
            arr = arr[:_DIM]
        norm = float(np.linalg.norm(arr))
        return arr / norm if norm > 0.0 else arr

    # ── registration ──────────────────────────────────────────────────────────

    def register_identity(
        self,
        stream_id: str,
        embedding: list[float] | np.ndarray,
        identity_id: str,
        confidence: float = 1.0,
    ) -> None:
        """
        Add or update an identity in the global index.

        Accepts appearance or combined embeddings.  Already-registered
        identities are updated in place so re-identification across sessions
        uses the most recent embedding.  Records created_at / last_seen /
        confidence for TTL and decay.
        """
        if not len(embedding):
            return
        normed = self._normalize(embedding)
        now = time.monotonic()

        with self._lock:
            self._maybe_purge(now)

            # Update existing entry if identity_id already present
            try:
                existing_idx = self._identity_ids.index(identity_id)
                self._embeddings[existing_idx] = normed
                self._stream_ids[existing_idx] = stream_id
                self._last_seen[identity_id] = now
                self._confidence[identity_id] = confidence
                # FAISS index cannot update in-place — rebuild lazily on next search
                if self._faiss_available:
                    self._rebuild_faiss()
                return
            except ValueError:
                pass  # new identity

            self._embeddings.append(normed)
            self._identity_ids.append(identity_id)
            self._stream_ids.append(stream_id)
            self._created_at[identity_id] = now
            self._last_seen[identity_id] = now
            self._confidence[identity_id] = confidence

            if self._faiss_available and self._faiss_index is not None:
                import faiss
                vec = normed.reshape(1, -1).copy()
                faiss.normalize_L2(vec)
                self._faiss_index.add(vec)

    def _rebuild_faiss(self) -> None:
        import faiss
        self._faiss_index = faiss.IndexFlatIP(_DIM)
        if self._embeddings:
            matrix = np.stack(self._embeddings, axis=0)
            faiss.normalize_L2(matrix)
            self._faiss_index.add(matrix)

    # ── TTL + decay ───────────────────────────────────────────────────────────

    def _maybe_purge(self, now: float) -> None:
        """Trigger a TTL purge at most once per _PURGE_INTERVAL seconds."""
        if now - self._last_purge < _PURGE_INTERVAL:
            return
        self._last_purge = now
        self._purge_expired(now)

    def _purge_expired(self, now: float | None = None) -> int:
        """
        Remove identities unseen for longer than _TTL_SECONDS.

        Returns the number of identities purged.  Caller must hold self._lock.
        """
        if now is None:
            now = time.monotonic()
        expired_ids = [
            iid for iid, last_seen in self._last_seen.items()
            if now - last_seen > _TTL_SECONDS
        ]
        if not expired_ids:
            return 0

        expired_set = set(expired_ids)
        keep = [i for i, iid in enumerate(self._identity_ids) if iid not in expired_set]
        self._embeddings = [self._embeddings[i] for i in keep]
        self._identity_ids = [self._identity_ids[i] for i in keep]
        self._stream_ids = [self._stream_ids[i] for i in keep]
        for iid in expired_ids:
            self._created_at.pop(iid, None)
            self._last_seen.pop(iid, None)
            self._confidence.pop(iid, None)

        if self._faiss_available:
            self._rebuild_faiss()

        try:
            from inference.monitoring.metrics import get_metrics
            get_metrics().record_expired_identity(len(expired_ids))
        except Exception:
            pass

        logger.info(
            "GlobalIdentityRegistry: purged %d expired identities (TTL=%ds)",
            len(expired_ids), int(_TTL_SECONDS),
        )
        return len(expired_ids)

    def _decayed_confidence(self, identity_id: str, now: float) -> float:
        """Return the time-decayed confidence score for an identity."""
        conf = self._confidence.get(identity_id, 1.0)
        last_seen = self._last_seen.get(identity_id)
        if last_seen is None:
            return round(conf, 4)
        elapsed = max(0.0, now - last_seen)
        return round(float(conf * math.exp(-_CONF_DECAY_LAMBDA * elapsed)), 4)

    # ── search ────────────────────────────────────────────────────────────────

    def search_global(
        self,
        embedding: list[float] | np.ndarray,
        k: int = 5,
        exclude_stream: str | None = None,
    ) -> list[dict]:
        """
        Return up to k matching identities from the global index.

        Only results with cosine similarity >= _CROSS_STREAM_THRESHOLD are
        returned.  Pass exclude_stream to skip identities registered by the
        querying stream (avoids matching a stream against itself).

        Each result includes a decayed ``confidence`` score in addition to
        the raw cosine ``score``.

        Returns: list of {"identity_id": str, "score": float, "stream_id": str, "confidence": float}
        """
        if not len(embedding):
            return []
        normed = self._normalize(embedding)
        now = time.monotonic()

        with self._lock:
            self._maybe_purge(now)
            if not self._embeddings:
                return []
            if self._faiss_available and self._faiss_index is not None and self._faiss_index.ntotal > 0:
                results = self._faiss_search(normed, k, exclude_stream)
            else:
                results = self._numpy_search(normed, k, exclude_stream)

            # Annotate each result with decayed confidence
            for hit in results:
                hit["confidence"] = self._decayed_confidence(hit["identity_id"], now)
            return results

    def _faiss_search(
        self,
        normed: np.ndarray,
        k: int,
        exclude_stream: str | None,
    ) -> list[dict]:
        import faiss
        oversample_k = min(k * 3, len(self._embeddings))
        vec = normed.reshape(1, -1).copy()
        faiss.normalize_L2(vec)
        scores, indices = self._faiss_index.search(vec, oversample_k)
        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or float(score) < _CROSS_STREAM_THRESHOLD:
                continue
            sid = self._stream_ids[idx]
            if exclude_stream and sid == exclude_stream:
                continue
            results.append({
                "identity_id": self._identity_ids[idx],
                "score": round(float(score), 4),
                "stream_id": sid,
            })
            if len(results) >= k:
                break
        return results

    def _numpy_search(
        self,
        normed: np.ndarray,
        k: int,
        exclude_stream: str | None,
    ) -> list[dict]:
        matrix = np.stack(self._embeddings, axis=0)   # (N, 512)
        scores = matrix @ normed                        # (N,) cosine similarities
        ranked = np.argsort(-scores)
        results: list[dict] = []
        for idx in ranked:
            score = float(scores[idx])
            if score < _CROSS_STREAM_THRESHOLD:
                break
            sid = self._stream_ids[idx]
            if exclude_stream and sid == exclude_stream:
                continue
            results.append({
                "identity_id": self._identity_ids[idx],
                "score": round(score, 4),
                "stream_id": sid,
            })
            if len(results) >= k:
                break
        return results

    # ── introspection ─────────────────────────────────────────────────────────

    @property
    def total_identities(self) -> int:
        with self._lock:
            return len(self._identity_ids)

    def stream_identity_counts(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for sid in self._stream_ids:
                counts[sid] = counts.get(sid, 0) + 1
            return counts

    def force_purge(self) -> int:
        """Explicitly trigger TTL purge. Returns number of expired identities removed."""
        with self._lock:
            return self._purge_expired()


# Process-wide singleton
_registry: GlobalIdentityRegistry = GlobalIdentityRegistry()


def get_global_registry() -> GlobalIdentityRegistry:
    """Return the process-wide GlobalIdentityRegistry singleton."""
    return _registry
