"""
IdentityProfileStore — thread-safe persistent store for identity profiles,
face enrollments, and identity match records.

Persistence strategy:
- identities.jsonl   — one JSON object per line; rewritten atomically on update
- enrollments.jsonl  — append-only; internal full records (never served raw)
- matches.jsonl      — append-only; recent MAX_RECENT_MATCHES kept in memory

Security:
- Raw embedding vectors are never stored in these records.
- to_public_dict() is used on FaceEnrollment before any API response.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Resolve project root so imports work regardless of working directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.models.identity_models import (
    FaceEnrollment,
    IdentityEnrollmentProfile,
    IdentityMatchRecord,
    IdentityProfile,
    IdentityStatus,
)


class IdentityProfileStore:
    """Thread-safe persistent store for identity profiles, enrollments, and matches."""

    MAX_RECENT_MATCHES = 500

    def __init__(self, store_dir: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        if store_dir is None:
            base = Path(__file__).resolve().parent.parent.parent
            store_dir = str(base / "storage" / "identities")
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._identities: Dict[str, IdentityProfile] = {}
        self._enrollments: Dict[str, List[FaceEnrollment]] = {}  # identity_id -> list
        self._enrollment_profiles: Dict[str, IdentityEnrollmentProfile] = {}
        self._recent_matches: deque = deque(maxlen=self.MAX_RECENT_MATCHES)

        self._load()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _identities_path(self) -> Path:
        return self._store_dir / "identities.jsonl"

    def _enrollments_path(self) -> Path:
        return self._store_dir / "enrollments.jsonl"

    def _matches_path(self) -> Path:
        return self._store_dir / "matches.jsonl"

    def _enrollment_profiles_path(self) -> Path:
        return self._store_dir / "enrollment_profiles.jsonl"

    # ------------------------------------------------------------------
    # Bootstrap persistence load
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load existing data from JSONL files on disk."""
        with self._lock:
            # Load identities
            if self._identities_path().exists():
                with open(self._identities_path(), "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            p = IdentityProfile.from_dict(d)
                            self._identities[p.identity_id] = p
                        except Exception as exc:
                            logger.warning("Failed to load identity record: %s", exc)

            # Load enrollments
            if self._enrollments_path().exists():
                with open(self._enrollments_path(), "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            e = FaceEnrollment.from_dict(d)
                            if e.identity_id not in self._enrollments:
                                self._enrollments[e.identity_id] = []
                            self._enrollments[e.identity_id].append(e)
                        except Exception as exc:
                            logger.warning("Failed to load enrollment record: %s", exc)

            # Load recent matches (keep only last MAX_RECENT_MATCHES)
            if self._matches_path().exists():
                matches_raw: List[IdentityMatchRecord] = []
                with open(self._matches_path(), "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            matches_raw.append(IdentityMatchRecord.from_dict(d))
                        except Exception as exc:
                            logger.warning("Failed to load match record: %s", exc)
                for m in matches_raw[-self.MAX_RECENT_MATCHES:]:
                    self._recent_matches.append(m)

            if self._enrollment_profiles_path().exists():
                with open(self._enrollment_profiles_path(), "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            profile = IdentityEnrollmentProfile.from_dict(d)
                            self._enrollment_profiles[profile.enrollment_id] = profile
                        except Exception as exc:
                            logger.warning("Failed to load enrollment profile: %s", exc)

        logger.info(
            "IdentityProfileStore loaded: %d identities, %d enrollments, %d enrollment profiles, %d recent matches",
            len(self._identities),
            sum(len(v) for v in self._enrollments.values()),
            len(self._enrollment_profiles),
            len(self._recent_matches),
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _append_jsonl(self, path: Path, data: dict) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(data) + "\n")

    def _rewrite_identities(self) -> None:
        """Atomically rewrite identities JSONL after an in-place update."""
        tmp = self._identities_path().with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for p in self._identities.values():
                fh.write(json.dumps(p.to_dict()) + "\n")
        tmp.replace(self._identities_path())

    def _rewrite_enrollments(self) -> None:
        tmp = self._enrollments_path().with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for enrollments in self._enrollments.values():
                for enrollment in enrollments:
                    fh.write(json.dumps(enrollment.to_dict()) + "\n")
        tmp.replace(self._enrollments_path())

    def _rewrite_enrollment_profiles(self) -> None:
        tmp = self._enrollment_profiles_path().with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for profile in self._enrollment_profiles.values():
                fh.write(json.dumps(profile.to_dict()) + "\n")
        tmp.replace(self._enrollment_profiles_path())

    # ------------------------------------------------------------------
    # Identity CRUD
    # ------------------------------------------------------------------

    def create_identity(
        self,
        display_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> IdentityProfile:
        with self._lock:
            profile = IdentityProfile(
                display_name=display_name,
                tags=tags or [],
                notes=notes,
                metadata=metadata or {},
            )
            self._identities[profile.identity_id] = profile
            self._append_jsonl(self._identities_path(), profile.to_dict())
            return profile

    def update_identity(
        self, identity_id: str, updates: dict
    ) -> Optional[IdentityProfile]:
        with self._lock:
            if identity_id not in self._identities:
                return None
            profile = self._identities[identity_id]
            allowed = {"display_name", "status", "tags", "notes", "metadata"}
            for k, v in updates.items():
                if k in allowed:
                    setattr(profile, k, v)
            profile.updated_at = time.time()
            self._rewrite_identities()
            return profile

    def get_identity(self, identity_id: str) -> Optional[IdentityProfile]:
        with self._lock:
            return self._identities.get(identity_id)

    def list_identities(
        self,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
    ) -> List[IdentityProfile]:
        with self._lock:
            results = list(self._identities.values())
            if status:
                results = [p for p in results if p.status == status]
            if tag:
                results = [p for p in results if tag in p.tags]
            return results[:limit]

    def archive_identity(self, identity_id: str) -> bool:
        with self._lock:
            if identity_id not in self._identities:
                return False
            self._identities[identity_id].status = IdentityStatus.ARCHIVED
            self._identities[identity_id].updated_at = time.time()
            self._rewrite_identities()
            return True

    # ------------------------------------------------------------------
    # Face enrollment operations
    # ------------------------------------------------------------------

    def add_face_enrollment(
        self,
        identity_id: str,
        image_path: Optional[str] = None,
        embedding: Any = None,
        quality_score: Optional[float] = None,
        status: str = "accepted",
        rejection_reasons: Optional[list[str]] = None,
        quality_metrics: Optional[dict] = None,
        source_breakdown: Optional[dict[str, float]] = None,
        batch_enrollment_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[FaceEnrollment]:
        with self._lock:
            if identity_id not in self._identities:
                return None
            # Store only an opaque reference, never the raw embedding vector
            emb_ref = None
            if embedding is not None:
                emb_ref = f"emb:{identity_id}:{time.time()}"
            enrollment = FaceEnrollment(
                identity_id=identity_id,
                image_path=image_path,
                embedding_vector_ref=emb_ref,
                quality_score=quality_score,
                status=status,
                rejection_reasons=rejection_reasons or [],
                quality_metrics=quality_metrics or {},
                source_breakdown=source_breakdown or {},
                batch_enrollment_id=batch_enrollment_id,
                metadata=metadata or {},
            )
            if identity_id not in self._enrollments:
                self._enrollments[identity_id] = []
            self._enrollments[identity_id].append(enrollment)
            self._append_jsonl(self._enrollments_path(), enrollment.to_dict())
            return enrollment

    def list_face_enrollments(self, identity_id: str) -> List[FaceEnrollment]:
        with self._lock:
            return list(self._enrollments.get(identity_id, []))

    def create_enrollment_profile(
        self,
        identity_id: str,
        enrollment_id: Optional[str] = None,
        display_name: Optional[str] = None,
        status: str = "completed",
        total_images: int = 0,
        accepted_images: int = 0,
        rejected_images: int = 0,
        aggregate_method: str = "mean",
        aggregate_embedding_ref: Optional[str] = None,
        quality_summary: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> IdentityEnrollmentProfile:
        with self._lock:
            profile = IdentityEnrollmentProfile(
                identity_id=identity_id,
                enrollment_id=enrollment_id,
                display_name=display_name,
                status=status,
                total_images=total_images,
                accepted_images=accepted_images,
                rejected_images=rejected_images,
                aggregate_method=aggregate_method,
                aggregate_embedding_ref=aggregate_embedding_ref,
                quality_summary=quality_summary or {},
                metadata=metadata or {},
            )
            self._enrollment_profiles[profile.enrollment_id] = profile
            self._append_jsonl(self._enrollment_profiles_path(), profile.to_dict())
            return profile

    def get_enrollment_profile(self, enrollment_id: str) -> Optional[IdentityEnrollmentProfile]:
        with self._lock:
            return self._enrollment_profiles.get(enrollment_id)

    def list_enrollment_profiles(
        self,
        identity_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[IdentityEnrollmentProfile]:
        with self._lock:
            profiles = list(self._enrollment_profiles.values())
            if identity_id:
                profiles = [profile for profile in profiles if profile.identity_id == identity_id]
            profiles.sort(key=lambda item: item.created_at, reverse=True)
            return profiles[:limit]

    def delete_enrollment_profile(self, enrollment_id: str) -> bool:
        with self._lock:
            profile = self._enrollment_profiles.pop(enrollment_id, None)
            if profile is None:
                return False
            for identity_id, enrollments in list(self._enrollments.items()):
                kept = [
                    enrollment
                    for enrollment in enrollments
                    if enrollment.batch_enrollment_id != enrollment_id
                ]
                self._enrollments[identity_id] = kept
            self._rewrite_enrollment_profiles()
            self._rewrite_enrollments()
            return True

    # ------------------------------------------------------------------
    # Match record operations
    # ------------------------------------------------------------------

    def record_match(
        self,
        identity_id: str,
        camera_id: Optional[str] = None,
        track_id: Optional[int] = None,
        confidence: float = 0.0,
        source: str = "face",
        source_breakdown: Optional[dict[str, float]] = None,
        quality_score: Optional[float] = None,
        operator_review_required: bool = True,
        match_type: str = "possible_identity_match",
        metadata: Optional[dict] = None,
    ) -> IdentityMatchRecord:
        with self._lock:
            record = IdentityMatchRecord(
                identity_id=identity_id,
                camera_id=camera_id,
                track_id=track_id,
                confidence=confidence,
                source=source,
                source_breakdown=source_breakdown or {},
                quality_score=quality_score,
                operator_review_required=operator_review_required,
                match_type=match_type,
                metadata=metadata or {},
            )
            self._recent_matches.append(record)
            self._append_jsonl(self._matches_path(), record.to_dict())
            return record

    def list_matches(
        self,
        identity_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[IdentityMatchRecord]:
        with self._lock:
            results = list(self._recent_matches)
            if identity_id:
                results = [m for m in results if m.identity_id == identity_id]
            return results[-limit:]


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_store_instance: Optional[IdentityProfileStore] = None
_store_lock = threading.Lock()


def get_identity_store() -> IdentityProfileStore:
    """Return (or lazily create) the process-wide IdentityProfileStore singleton."""
    global _store_instance
    with _store_lock:
        if _store_instance is None:
            _store_instance = IdentityProfileStore()
        return _store_instance
