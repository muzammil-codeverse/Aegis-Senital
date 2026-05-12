import pytest

from app.services.identity_candidate_service import (
    get_identity_candidate_service,
    reset_identity_candidate_service_for_tests,
)


def test_fusion_payload_creates_pending_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_IDENTITY_CANDIDATES_STORE", str(tmp_path / "c.json"))
    reset_identity_candidate_service_for_tests()
    svc = get_identity_candidate_service()
    row = svc.upsert_from_fusion_payload(
        {
            "global_identity_id": "gid_test_emit",
            "camera_id": "cam1",
            "face_score": 0.6,
            "reid_score": 0.55,
            "fusion_score": 0.58,
            "track_continuity_score": 0.5,
            "quality_score": 0.7,
            "liveness_enabled_snapshot": False,
            "liveness_status": "disabled",
            "camera_observations": [],
            "first_seen": 1.0,
            "last_seen": 2.0,
            "evidence_refs": [],
        }
    )
    assert row["review_status"] == "pending"
    assert row.get("global_identity_id") == "gid_test_emit"


def test_list_candidates_excludes_rejected_surfacing(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_IDENTITY_CANDIDATES_STORE", str(tmp_path / "c.json"))
    reset_identity_candidate_service_for_tests()
    svc = get_identity_candidate_service()
    rid = svc.upsert_from_fusion_payload(
        {
            "global_identity_id": "gid_rej",
            "camera_id": "cam1",
            "face_score": 0.5,
            "reid_score": 0.5,
            "fusion_score": 0.5,
            "track_continuity_score": 0.5,
            "liveness_enabled_snapshot": False,
            "liveness_status": "disabled",
            "camera_observations": [],
            "first_seen": 1.0,
            "last_seen": 2.0,
            "evidence_refs": [],
        }
    )["identity_candidate_id"]
    svc.reject_candidate(rid, reviewed_by="t", review_notes="no")
    listed = svc.list_candidates(exclude_rejected_surfacing=True)
    assert all(not r.get("exclude_from_high_confidence_surfacing") for r in listed)
