from __future__ import annotations

import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import numpy as np
import faiss  # type: ignore

logger = logging.getLogger(__name__)

_REBUILD_THRESHOLD = 50  # lazy full-rebuild after this many in-place updates


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_embedding(embedding: list[float] | np.ndarray | None, dim: int) -> np.ndarray:
    if embedding is None:
        raise RuntimeError("Embedding required - identity system cannot run without real model output.")
    arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise RuntimeError("Empty embedding received - identity system cannot run without real model output.")
    if arr.size < dim:
        arr = np.pad(arr, (0, dim - arr.size))
    elif arr.size > dim:
        arr = arr[:dim]
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        raise RuntimeError("Zero-norm embedding received - dummy embeddings are not permitted.")
    return arr / norm


class VectorStore:
    """
    Identity embedding store with FAISS search.

    Upsert strategy:
      NEW identity  → O(1) incremental index.add()
      UPDATE        → update in-memory record; defer full index rebuild until
                      _REBUILD_THRESHOLD cumulative updates have accumulated.

    This eliminates the O(n) full rebuild that previously ran on every
    upsert call, reducing write cost from O(n) to amortised O(1).
    """

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._indices: dict[str, Any] = {
            "face": faiss.IndexFlatIP(dim),
            "appearance": faiss.IndexFlatIP(dim),
        }
        self._id_order: dict[str, list[str]] = {"face": [], "appearance": []}
        self._dirty_count: dict[str, int] = {"face": 0, "appearance": 0}

    @property
    def dim(self) -> int:
        return self._dim

    def upsert_identity(
        self,
        identity_id: str,
        *,
        face_embedding: list[float] | np.ndarray | None = None,
        appearance_embedding: list[float] | np.ndarray | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if face_embedding is None or appearance_embedding is None:
            raise RuntimeError("Vector DB required - identity system cannot persist incomplete embeddings.")
        with self._lock:
            is_new = identity_id not in self._records
            record = self._records.setdefault(
                identity_id,
                {
                    "identity_id": identity_id,
                    "face_embedding": _normalize_embedding(face_embedding, self._dim),
                    "appearance_embedding": _normalize_embedding(appearance_embedding, self._dim),
                    "metadata": {},
                    "updated_at": _now_iso(),
                },
            )
            record["face_embedding"] = _normalize_embedding(face_embedding, self._dim)
            record["appearance_embedding"] = _normalize_embedding(appearance_embedding, self._dim)
            if metadata:
                record["metadata"].update(metadata)
            record["updated_at"] = _now_iso()

            if is_new:
                # Incremental O(1) add for brand-new identities (the common path)
                for modality, key in (("face", "face_embedding"), ("appearance", "appearance_embedding")):
                    vec = record[key].reshape(1, -1).astype(np.float32)
                    self._indices[modality].add(vec)
                    self._id_order[modality].append(identity_id)
            else:
                # Existing identity: update in-memory record and defer index rebuild
                self._dirty_count["face"] += 1
                self._dirty_count["appearance"] += 1
                if self._dirty_count["face"] >= _REBUILD_THRESHOLD:
                    self._full_rebuild_locked()

    def get_identity(self, identity_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(identity_id)
            if record is None:
                return None
            return self._serialise_record(record)

    def search_top_k(
        self,
        embedding: list[float] | np.ndarray | None,
        k: int = 5,
        *,
        modality: str = "appearance",
    ) -> list[dict[str, Any]]:
        modality = self._validate_modality(modality)
        query = _normalize_embedding(embedding, self._dim)
        with self._lock:
            identities = self._id_order[modality]
            if not identities:
                return []
            top_k = max(1, min(k, len(identities)))
            scores, indices = self._indices[modality].search(query.reshape(1, -1), top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(identities):
                    continue
                identity_id = identities[idx]
                record = self._records.get(identity_id)
                if record is None:
                    continue
                results.append(
                    {
                        "identity_id": identity_id,
                        "score": float(score),
                        "modality": modality,
                        "metadata": deepcopy(record["metadata"]),
                    }
                )
            return results

    def all_identities(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._serialise_record(record) for record in self._records.values()]

    def _full_rebuild_locked(self) -> None:
        """Full index rebuild — called lazily after _REBUILD_THRESHOLD in-place updates."""
        for modality in ("face", "appearance"):
            rows: list[np.ndarray] = []
            order: list[str] = []
            for identity_id, record in self._records.items():
                vector = record[f"{modality}_embedding"]
                if float(np.linalg.norm(vector)) == 0.0:
                    continue
                rows.append(vector)
                order.append(identity_id)
            self._id_order[modality] = order
            index = faiss.IndexFlatIP(self._dim)
            if rows:
                index.add(np.vstack(rows).astype(np.float32))
            self._indices[modality] = index
        self._dirty_count = {"face": 0, "appearance": 0}
        logger.debug("VectorStore: full index rebuild completed (%d identities).", len(self._records))

    def _serialise_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity_id": record["identity_id"],
            "face_embedding": record["face_embedding"].astype(float).tolist(),
            "appearance_embedding": record["appearance_embedding"].astype(float).tolist(),
            "metadata": deepcopy(record["metadata"]),
            "updated_at": record["updated_at"],
        }

    @staticmethod
    def _validate_modality(modality: str) -> str:
        if modality not in {"face", "appearance"}:
            raise ValueError(f"Unsupported modality '{modality}'. Expected 'face' or 'appearance'.")
        return modality
