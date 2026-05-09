from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HandoffState(str, Enum):
    PREDICTED = "predicted"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class HandoffEvidence:
    topology_score: float = 0.0
    temporal_score: float = 0.0
    motion_score: float = 0.0
    appearance_score: float | None = None
    face_score: float | None = None
    identity_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "topology_score": self.topology_score,
            "temporal_score": self.temporal_score,
            "motion_score": self.motion_score,
            "appearance_score": self.appearance_score,
            "face_score": self.face_score,
            "identity_score": self.identity_score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffEvidence":
        return cls(
            topology_score=float(d.get("topology_score", 0.0)),
            temporal_score=float(d.get("temporal_score", 0.0)),
            motion_score=float(d.get("motion_score", 0.0)),
            appearance_score=d.get("appearance_score"),
            face_score=d.get("face_score"),
            identity_score=d.get("identity_score"),
        )


@dataclass
class HandoffPrediction:
    handoff_id: str
    state: str = HandoffState.PREDICTED.value
    source_camera: str = ""
    target_camera: str = ""
    source_track_id: int | None = None
    target_track_id: int | None = None
    identity_id: str | None = None
    predicted_at: float = 0.0
    candidate_seen_at: float | None = None
    confirmed_at: float | None = None
    eta_seconds: float | None = None
    confidence: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    route: list[str] = field(default_factory=list)
    reason: str = ""
    expires_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "handoff_id": self.handoff_id,
            "state": self.state,
            "source_camera": self.source_camera,
            "target_camera": self.target_camera,
            "source_track_id": self.source_track_id,
            "target_track_id": self.target_track_id,
            "identity_id": self.identity_id,
            "predicted_at": self.predicted_at,
            "candidate_seen_at": self.candidate_seen_at,
            "confirmed_at": self.confirmed_at,
            "eta_seconds": self.eta_seconds,
            "confidence": self.confidence,
            "score_breakdown": self.score_breakdown,
            "evidence": self.evidence,
            "route": self.route,
            "reason": self.reason,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffPrediction":
        return cls(
            handoff_id=str(d.get("handoff_id", "")),
            state=str(d.get("state", HandoffState.PREDICTED.value)),
            source_camera=str(d.get("source_camera", "")),
            target_camera=str(d.get("target_camera", "")),
            source_track_id=d.get("source_track_id"),
            target_track_id=d.get("target_track_id"),
            identity_id=d.get("identity_id"),
            predicted_at=float(d.get("predicted_at", 0.0)),
            candidate_seen_at=d.get("candidate_seen_at"),
            confirmed_at=d.get("confirmed_at"),
            eta_seconds=d.get("eta_seconds"),
            confidence=float(d.get("confidence", 0.0)),
            score_breakdown=dict(d.get("score_breakdown") or {}),
            evidence=dict(d.get("evidence") or {}),
            route=list(d.get("route") or []),
            reason=str(d.get("reason", "")),
            expires_at=float(d.get("expires_at", 0.0)),
            metadata=dict(d.get("metadata") or {}),
        )


# Aliases for clarity
HandoffCandidate = HandoffPrediction
HandoffEvent = HandoffPrediction
