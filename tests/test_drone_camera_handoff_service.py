"""Tests for Phase 46 HandoffService."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


class _MockUser:
    username = "test"
    role = "admin"
    user_id = "u1"


class _MockGisRepo:
    def list_camera_geo_profiles(self, user):
        class _P:
            camera_id = "cam_nearby"
            name = "Nearby Camera"
            latitude = 30.1578
            longitude = 71.5252
            metadata = {}
        return [_P()]


def _can_access(cam_id, user):
    return cam_id != "forbidden"


def _make_repo(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    return DroneFusionRepository(root_dir=tmp_path / "fusion_handoff")


def test_suggest_handoffs_near_location(monkeypatch, tmp_path):
    import app.services.drone_fusion.handoff_service as hs_mod
    monkeypatch.setattr(hs_mod, "can_access_camera", _can_access)

    from app.services.drone_fusion.handoff_service import HandoffService
    repo = _make_repo(tmp_path)
    svc = HandoffService(repository=repo, gis_repo=_MockGisRepo())

    handoffs = svc.suggest_handoffs_near_location(30.1575, 71.5249, 200.0, _MockUser())
    assert len(handoffs) > 0
    h = handoffs[0]
    assert h.operator_review_required is True
    assert h.from_source_type == "drone_simulation"
    assert h.to_source_type == "fixed_camera"
    assert 0.0 < h.confidence <= 1.0


def test_handoff_safe_summary_no_forbidden(monkeypatch, tmp_path):
    import app.services.drone_fusion.handoff_service as hs_mod
    monkeypatch.setattr(hs_mod, "can_access_camera", _can_access)

    from app.services.drone_fusion.handoff_service import HandoffService
    from app.models.drone_fusion_models import FORBIDDEN_PHRASES
    repo = _make_repo(tmp_path)
    svc = HandoffService(repository=repo, gis_repo=_MockGisRepo())

    handoffs = svc.suggest_handoffs_near_location(30.1575, 71.5249, 200.0, _MockUser())
    for h in handoffs:
        lower = h.safe_summary.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lower, f"Forbidden phrase '{phrase}' in handoff safe_summary"


def test_handoff_persisted_in_repo(monkeypatch, tmp_path):
    import app.services.drone_fusion.handoff_service as hs_mod
    monkeypatch.setattr(hs_mod, "can_access_camera", _can_access)

    from app.services.drone_fusion.handoff_service import HandoffService
    repo = _make_repo(tmp_path)
    svc = HandoffService(repository=repo, gis_repo=_MockGisRepo())

    svc.suggest_handoffs_near_location(30.1575, 71.5249, 200.0, _MockUser())
    stored = repo.list_handoffs()
    assert len(stored) > 0


def test_no_handoffs_for_empty_gis(monkeypatch, tmp_path):
    import app.services.drone_fusion.handoff_service as hs_mod
    monkeypatch.setattr(hs_mod, "can_access_camera", _can_access)

    class _EmptyGis:
        def list_camera_geo_profiles(self, user):
            return []

    from app.services.drone_fusion.handoff_service import HandoffService
    repo = _make_repo(tmp_path)
    svc = HandoffService(repository=repo, gis_repo=_EmptyGis())
    handoffs = svc.suggest_handoffs_near_location(30.1575, 71.5249, 200.0, _MockUser())
    assert handoffs == []
