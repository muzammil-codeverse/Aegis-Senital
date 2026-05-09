"""
Identity domain models for Aegis Sentinel Phase 20.

Provides plain Python objects (no ORM dependency) for identity profiles,
face enrollments, watchlist entries, and match records.  All objects
support to_dict / from_dict round-trips and thread-safe instantiation.

Security notes:
- FaceEnrollment.to_public_dict() strips raw image paths and embedding
  vector references before any record leaves this layer.
- Embedding vectors are never stored in these models; the store layer
  uses only opaque reference strings.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class IdentityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    WATCHLISTED = "watchlisted"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class WatchlistSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# IdentityProfile
# ---------------------------------------------------------------------------

class IdentityProfile:
    """Represents a tracked person identity managed by the system."""

    def __init__(
        self,
        identity_id: Optional[str] = None,
        display_name: Optional[str] = None,
        status: str = IdentityStatus.ACTIVE,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        self.identity_id: str = identity_id or str(uuid.uuid4())
        self.display_name: Optional[str] = display_name
        self.status: str = status
        self.tags: List[str] = tags or []
        self.notes: Optional[str] = notes
        self.metadata: Dict = metadata or {}
        now = time.time()
        self.created_at: float = now
        self.updated_at: float = now

    def to_dict(self) -> dict:
        return {
            "identity_id": self.identity_id,
            "display_name": self.display_name,
            "status": self.status,
            "tags": self.tags,
            "notes": self.notes,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IdentityProfile":
        obj = cls.__new__(cls)
        obj.identity_id = d["identity_id"]
        obj.display_name = d.get("display_name")
        obj.status = d.get("status", IdentityStatus.ACTIVE)
        obj.tags = d.get("tags", [])
        obj.notes = d.get("notes")
        obj.metadata = d.get("metadata", {})
        obj.created_at = d.get("created_at", time.time())
        obj.updated_at = d.get("updated_at", time.time())
        return obj


# ---------------------------------------------------------------------------
# FaceEnrollment
# ---------------------------------------------------------------------------

class FaceEnrollment:
    """A single face image enrollment linked to an IdentityProfile."""

    def __init__(
        self,
        identity_id: str,
        image_path: Optional[str] = None,
        embedding_vector_ref: Optional[str] = None,
        quality_score: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        self.enrollment_id: str = str(uuid.uuid4())
        self.identity_id: str = identity_id
        self.image_path: Optional[str] = image_path
        self.embedding_vector_ref: Optional[str] = embedding_vector_ref
        self.quality_score: Optional[float] = quality_score
        self.metadata: Dict = metadata or {}
        self.created_at: float = time.time()

    def to_dict(self) -> dict:
        """Full internal representation — never expose publicly."""
        return {
            "enrollment_id": self.enrollment_id,
            "identity_id": self.identity_id,
            "image_path": self.image_path,
            "embedding_vector_ref": self.embedding_vector_ref,
            "quality_score": self.quality_score,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict:
        """Public-safe representation: strips raw paths and embedding refs."""
        d = self.to_dict()
        d.pop("image_path", None)
        d.pop("embedding_vector_ref", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FaceEnrollment":
        obj = cls.__new__(cls)
        obj.enrollment_id = d["enrollment_id"]
        obj.identity_id = d["identity_id"]
        obj.image_path = d.get("image_path")
        obj.embedding_vector_ref = d.get("embedding_vector_ref")
        obj.quality_score = d.get("quality_score")
        obj.metadata = d.get("metadata", {})
        obj.created_at = d.get("created_at", time.time())
        return obj


# ---------------------------------------------------------------------------
# WatchlistEntry
# ---------------------------------------------------------------------------

class WatchlistEntry:
    """A watchlist record linking an identity to a severity level and reason."""

    def __init__(
        self,
        identity_id: str,
        severity: str = WatchlistSeverity.MEDIUM,
        reason: Optional[str] = None,
        expires_at: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        self.watchlist_id: str = str(uuid.uuid4())
        self.identity_id: str = identity_id
        self.severity: str = severity
        self.reason: Optional[str] = reason
        self.active: bool = True
        self.created_at: float = time.time()
        self.expires_at: Optional[float] = expires_at
        self.metadata: Dict = metadata or {}

    def to_dict(self) -> dict:
        return {
            "watchlist_id": self.watchlist_id,
            "identity_id": self.identity_id,
            "severity": self.severity,
            "reason": self.reason,
            "active": self.active,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WatchlistEntry":
        obj = cls.__new__(cls)
        obj.watchlist_id = d["watchlist_id"]
        obj.identity_id = d["identity_id"]
        obj.severity = d.get("severity", WatchlistSeverity.MEDIUM)
        obj.reason = d.get("reason")
        obj.active = d.get("active", True)
        obj.created_at = d.get("created_at", time.time())
        obj.expires_at = d.get("expires_at")
        obj.metadata = d.get("metadata", {})
        return obj


# ---------------------------------------------------------------------------
# IdentityMatchRecord
# ---------------------------------------------------------------------------

class IdentityMatchRecord:
    """A single match event linking a track to a known identity."""

    def __init__(
        self,
        identity_id: str,
        camera_id: Optional[str] = None,
        track_id: Optional[int] = None,
        confidence: float = 0.0,
        source: str = "face",
        metadata: Optional[Dict] = None,
    ) -> None:
        self.match_id: str = str(uuid.uuid4())
        self.identity_id: str = identity_id
        self.camera_id: Optional[str] = camera_id
        self.track_id: Optional[int] = track_id
        self.confidence: float = confidence
        self.matched_at: float = time.time()
        self.source: str = source
        self.metadata: Dict = metadata or {}

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "identity_id": self.identity_id,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "confidence": self.confidence,
            "matched_at": self.matched_at,
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IdentityMatchRecord":
        obj = cls.__new__(cls)
        obj.match_id = d["match_id"]
        obj.identity_id = d["identity_id"]
        obj.camera_id = d.get("camera_id")
        obj.track_id = d.get("track_id")
        obj.confidence = d.get("confidence", 0.0)
        obj.matched_at = d.get("matched_at", time.time())
        obj.source = d.get("source", "face")
        obj.metadata = d.get("metadata", {})
        return obj
