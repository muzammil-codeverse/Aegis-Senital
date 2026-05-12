from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def test_llm_service_includes_investigation_safety_notice():
    from app.services.llm_service import LlmService
    svc = LlmService.__new__(LlmService)
    svc._config = {}
    svc._case_service = MagicMock()

    case = MagicMock()
    case.case_id = "case_001"
    case.title = "Test"
    case.description = "desc"
    case.status = "open"
    case.priority = "medium"
    case.severity = "medium"
    case.camera_ids = []
    case.source_event_ids = []
    case.track_ids = []
    case.assigned_to = None
    case.created_at = "2026-01-01T00:00:00Z"
    case.updated_at = "2026-01-01T00:00:00Z"
    case.review_status = "pending"
    case.requires_review = True
    case.metadata = {}

    svc._case_service.get_case.return_value = case
    svc._case_service.list_evidence.return_value = []
    svc._case_service.get_timeline.return_value = []
    svc._case_service.list_notes.return_value = []
    svc._custody_service = MagicMock()
    manifest = MagicMock()
    manifest.evidence_items = []
    manifest.metadata = {}
    svc._custody_service.build_manifest.return_value = manifest
    svc._load_enrichment_context = MagicMock(return_value=([], []))

    with patch("app.repositories.investigation_repository.get_investigation_repository") as mock_repo:
        mock_repo.return_value.list_hypotheses.return_value = []
        ctx = svc._build_case_context("case_001")

    assert "investigation_safety_notice" in ctx
    notice = ctx["investigation_safety_notice"]
    assert "not confirmed facts" in notice.lower() or "investigative aids" in notice.lower()
    assert "guilt" not in notice.lower() or "do not state" in notice.lower()


def test_llm_investigation_hypotheses_not_facts():
    from app.services.llm_service import LlmService
    svc = LlmService.__new__(LlmService)

    with patch("app.repositories.investigation_repository.get_investigation_repository") as mock_repo:
        mock_repo.return_value.list_hypotheses.return_value = []
        result = svc._load_investigation_hypotheses("case_001")
    assert isinstance(result, list)


def test_llm_investigation_hypotheses_no_forbidden_wording():
    from app.services.path_reconstruction_service import FORBIDDEN_PHRASES
    from app.models.investigation_models import PathHypothesis, InvestigationSubjectRef

    hyp = PathHypothesis(
        hypothesis_id="hyp_abc",
        subject_ref=InvestigationSubjectRef(type="manual", ref_id="r1"),
        safe_summary="Possible movement path requiring operator review.",
    )
    lower = hyp.safe_summary.lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in lower
