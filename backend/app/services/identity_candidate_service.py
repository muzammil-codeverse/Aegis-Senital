"""Identity candidate listing and review (never auto-confirms identity)."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.repositories.identity_candidate_repository import (
    IdentityCandidateRepository,
    get_identity_candidate_repository,
)
from inference.identity.runtime_config import load_identity_config

logger = logging.getLogger(__name__)


def _public_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Strip fields that should not leave the trust boundary."""
    out = dict(row)
    out.pop("internal_debug", None)
    return out


def explainability_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "wording": {
            "match_label": "Possible identity match",
            "review_label": "Requires operator review",
            "liveness_note": (
                "Liveness disabled"
                if not row.get("liveness_enabled_snapshot")
                else ("Liveness unavailable" if row.get("liveness_status") in {None, "unavailable", "failed"} else str(row.get("liveness_status")))
            ),
        },
        "face_score": row.get("face_score"),
        "reid_score": row.get("reid_score"),
        "fusion_score": row.get("fusion_score"),
        "track_continuity_score": row.get("track_continuity_score"),
        "quality_score": row.get("quality_score"),
        "liveness_status": row.get("liveness_status"),
        "camera_observations": row.get("camera_observations") or [],
        "first_seen": row.get("first_seen"),
        "last_seen": row.get("last_seen"),
        "evidence_refs": row.get("evidence_refs") or [],
        "review_status": row.get("review_status"),
    }


class IdentityCandidateService:
    def __init__(self, repo: IdentityCandidateRepository | None = None) -> None:
        self._repo = repo or get_identity_candidate_repository()
        self._config = load_identity_config()

    def list_candidates(
        self,
        *,
        review_status: str | None = None,
        exclude_rejected_surfacing: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self._repo.list_all()
        out = []
        for row in rows:
            if review_status and str(row.get("review_status")) != review_status:
                continue
            if exclude_rejected_surfacing and row.get("exclude_from_high_confidence_surfacing"):
                continue
            out.append(_public_candidate(row))
        out.sort(key=lambda r: float(r.get("last_seen") or r.get("created_at") or 0.0), reverse=True)
        return out

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self._repo.get(candidate_id)
        return _public_candidate(row) if row else None

    def accept_candidate(
        self,
        candidate_id: str,
        *,
        reviewed_by: str | None,
        review_notes: str | None,
    ) -> dict[str, Any] | None:
        if bool((self._config.get("review") or {}).get("auto_confirm_identity", False)):
            logger.error("auto_confirm_identity must remain disabled")
        return self._repo.update_review(
            candidate_id,
            review_status="accepted",
            reviewed_by=reviewed_by,
            review_notes=review_notes,
            extra={"review_outcome": "accepted_for_tracking_only"},
        )

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        reviewed_by: str | None,
        review_notes: str | None,
    ) -> dict[str, Any] | None:
        if not bool((self._config.get("review") or {}).get("allow_reject_candidate", True)):
            return None
        return self._repo.update_review(
            candidate_id,
            review_status="rejected",
            reviewed_by=reviewed_by,
            review_notes=review_notes,
        )

    def escalate_candidate(
        self,
        candidate_id: str,
        *,
        reviewed_by: str | None,
        review_notes: str | None,
    ) -> dict[str, Any] | None:
        return self._repo.update_review(
            candidate_id,
            review_status="escalated",
            reviewed_by=reviewed_by,
            review_notes=review_notes,
        )

    def seed_demo_candidate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Test / demo helper — not used for production analytics."""
        payload = payload or {}
        base = {
            "identity_candidate_id": str(uuid.uuid4()),
            "global_identity_id": payload.get("global_identity_id"),
            "case_id": payload.get("case_id"),
            "camera_id": payload.get("camera_id") or "cam_demo",
            "source_event_id": payload.get("source_event_id") or "evt_demo",
            "face_score": 0.61,
            "reid_score": 0.55,
            "fusion_score": 0.59,
            "track_continuity_score": 0.52,
            "quality_score": 0.7,
            "liveness_status": "disabled",
            "liveness_enabled_snapshot": False,
            "camera_observations": [{"camera_id": "cam_demo", "frames": 3}],
            "first_seen": time.time() - 3600,
            "last_seen": time.time(),
            "evidence_refs": [{"type": "event_ref", "ref": "evt_demo"}],
            "review_status": "pending",
        }
        if payload:
            base.update({k: v for k, v in payload.items() if v is not None})
        return self._repo.upsert(base)


_service: IdentityCandidateService | None = None


def get_identity_candidate_service() -> IdentityCandidateService:
    global _service
    if _service is None:
        _service = IdentityCandidateService()
    return _service


def reset_identity_candidate_service_for_tests() -> None:
    global _service
    _service = None
