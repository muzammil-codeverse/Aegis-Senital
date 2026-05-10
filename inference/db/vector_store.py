from __future__ import annotations

import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import faiss  # type: ignore
import numpy as np

logger = logging.getLogger(__name__)


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

    Face and appearance embeddings are tracked independently so face-only
    enrollment can be stored before person ReID embeddings are available.
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
        if face_embedding is None and appearance_embedding is None:
            raise RuntimeError("Vector DB requires at least one embedding vector.")
        with self._lock:
            record = self._records.setdefault(
                identity_id,
                {
                    "identity_id": identity_id,
                    "face_embedding": None,
                    "appearance_embedding": None,
                    "metadata": {},
                    "updated_at": _now_iso(),
                },
            )
            if face_embedding is not None:
                record["face_embedding"] = _normalize_embedding(face_embedding, self._dim)
            if appearance_embedding is not None:
                record["appearance_embedding"] = _normalize_embedding(appearance_embedding, self._dim)
            if metadata:
                record["metadata"].update(metadata)
            record["updated_at"] = _now_iso()
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
        for modality in ("face", "appearance"):
            rows: list[np.ndarray] = []
            order: list[str] = []
            for identity_id, record in self._records.items():
                vector = record[f"{modality}_embedding"]
                if vector is None or float(np.linalg.norm(vector)) == 0.0:
                    continue
                rows.append(vector)
                order.append(identity_id)
            self._id_order[modality] = order
            index = faiss.IndexFlatIP(self._dim)
            if rows:
                index.add(np.vstack(rows).astype(np.float32))
            self._indices[modality] = index
        logger.debug("VectorStore: full index rebuild completed (%d identities).", len(self._records))

    def _serialise_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity_id": record["identity_id"],
            "face_embedding": (
                record["face_embedding"].astype(float).tolist()
                if record["face_embedding"] is not None else []
            ),
            "appearance_embedding": (
                record["appearance_embedding"].astype(float).tolist()
                if record["appearance_embedding"] is not None else []
            ),
            "metadata": deepcopy(record["metadata"]),
            "updated_at": record["updated_at"],
        }

    @staticmethod
    def _validate_modality(modality: str) -> str:
        if modality not in {"face", "appearance"}:
            raise ValueError(f"Unsupported modality '{modality}'. Expected 'face' or 'appearance'.")
        return modality
