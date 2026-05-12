from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.gis_models import CameraGeoProfile, EventGeoMarker
from app.models.investigation_models import PathReconstructionRequest
from app.models.security_models import UserAccount, UserStatus
from app.services.path_reconstruction_service import (
    INSUFFICIENT_DATA_MSG,
    SAFE_SUMMARY,
    FORBIDDEN_PHRASES,
    _safe_summary_check,
    reconstruct_path,
)


def _make_user(role: str = "analyst") -> UserAccount:
    return UserAccount(
        user_id=f"u-{role}",
        username=role,
        display_name=role,
        role=role,
        status=UserStatus.ACTIVE.value,
        password_hash="x",
        created_at=1.0,
        updated_at=1.0,
    )


def _make_gis_repo(with_cameras: bool = True, with_events: bool = True) -> MagicMock:
    repo = MagicMock()
    profiles = []
    if with_cameras:
        profiles = [
            CameraGeoProfile(camera_id="cam_01", name="Cam 1", latitude=30.150, longitude=71.520),
            CameraGeoProfile(camera_id="cam_02", name="Cam 2", latitude=30.151, longitude=71.521),
        ]
    repo.list_camera_geo_profiles.return_value = profiles

    markers = []
    if with_events:
        now = datetime.now(timezone.utc).isoformat()
        markers = [
            EventGeoMarker(
                event_id="evt_001",
                camera_id="cam_01",
                case_id="case_test",
                latitude=30.150,
                longitude=71.520,
                timestamp=now,
                severity="medium",
                risk_score=0.6,
            ),
        ]
    repo.get_event_markers.return_value = markers
    return repo


def _make_inv_repo() -> MagicMock:
    repo = MagicMock()
    repo.save_hypothesis.side_effect = lambda h: h
    return repo


def test_reconstruct_path_no_case_or_event_returns_insufficient():
    req = PathReconstructionRequest()
    resp = reconstruct_path(req, MagicMock(), MagicMock(), _make_user())
    assert resp.status == "insufficient_data"


def test_reconstruct_path_no_cameras_returns_insufficient():
    req = PathReconstructionRequest(case_id="case_001")
    gis = _make_gis_repo(with_cameras=False, with_events=False)
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    assert resp.status == "insufficient_data"


def test_reconstruct_path_no_events_returns_insufficient():
    req = PathReconstructionRequest(case_id="case_001")
    gis = _make_gis_repo(with_cameras=True, with_events=False)
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    assert resp.status == "insufficient_data"


def test_reconstruct_path_with_evidence_returns_ok():
    req = PathReconstructionRequest(case_id="case_test")
    gis = _make_gis_repo(with_cameras=True, with_events=True)
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    assert resp.status == "ok"
    assert resp.operator_review_required is True


def test_reconstruct_path_has_evidence_refs():
    req = PathReconstructionRequest(case_id="case_test")
    gis = _make_gis_repo(with_cameras=True, with_events=True)
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    if resp.status == "ok":
        assert resp.evidence_ref_count > 0


def test_reconstruct_path_no_identity_certainty():
    req = PathReconstructionRequest(case_id="case_test")
    gis = _make_gis_repo()
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    for hyp in resp.hypotheses:
        lower = hyp.safe_summary.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lower, f"Forbidden phrase found: {phrase}"


def test_safe_summary_check_blocks_forbidden():
    bad = "criminal confirmed — suspect attacker"
    result = _safe_summary_check(bad)
    assert result == SAFE_SUMMARY


def test_safe_summary_check_passes_clean():
    clean = "Possible movement path requiring operator review."
    assert _safe_summary_check(clean) == clean


def test_hypothesis_operator_review_required():
    req = PathReconstructionRequest(case_id="case_test")
    gis = _make_gis_repo()
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    for hyp in resp.hypotheses:
        assert hyp.operator_review_required is True


def test_hypothesis_review_status_starts_pending():
    req = PathReconstructionRequest(case_id="case_test")
    gis = _make_gis_repo()
    inv = _make_inv_repo()
    resp = reconstruct_path(req, gis, inv, _make_user())
    for hyp in resp.hypotheses:
        assert hyp.review_status == "pending"
