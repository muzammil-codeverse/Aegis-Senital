"""JSON persistence for identity match candidates pending operator review."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def _default_store_path() -> Path:
    override = (os.environ.get("SENTINEL_IDENTITY_CANDIDATES_STORE") or "").strip()
    if override:
        return Path(override)
    root = Path(__file__).resolve().parents[3]
    return root / "storage" / "identity_candidates" / "candidates.json"


class IdentityCandidateRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_store_path()
        self._lock = threading.RLock()
        self._candidates: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._candidates = {}
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._candidates = {}
                return
            raw = payload.get("candidates") if isinstance(payload, dict) else None
            if isinstance(raw, dict):
                self._candidates = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
            else:
                self._candidates = {}

    def _save_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        blob = {"version": 1, "candidates": self._candidates}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._candidates.values()]

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._candidates.get(candidate_id)
            return dict(row) if row else None

    def upsert(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            cid = str(row.get("identity_candidate_id") or uuid.uuid4())
            row = dict(row)
            row["identity_candidate_id"] = cid
            row.setdefault("review_status", "pending")
            row.setdefault("created_at", time.time())
            row["updated_at"] = time.time()
            self._candidates[cid] = row
            self._save_unlocked()
            return dict(row)

    def update_review(
        self,
        candidate_id: str,
        *,
        review_status: str,
        reviewed_by: str | None,
        review_notes: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._candidates.get(candidate_id)
            if not row:
                return None
            row = dict(row)
            row["review_status"] = review_status
            row["reviewed_by"] = reviewed_by
            row["reviewed_at"] = time.time()
            if review_notes is not None:
                row["review_notes"] = review_notes
            if extra:
                row.update(extra)
            row["updated_at"] = time.time()
            if review_status == "rejected":
                row["exclude_from_high_confidence_surfacing"] = True
            self._candidates[candidate_id] = row
            self._save_unlocked()
            return dict(row)


_repo: IdentityCandidateRepository | None = None


def get_identity_candidate_repository() -> IdentityCandidateRepository:
    global _repo
    if _repo is None:
        _repo = IdentityCandidateRepository()
    return _repo


def reset_identity_candidate_repository_for_tests(path: Path | None = None) -> None:
    global _repo
    _repo = IdentityCandidateRepository(path=path)
