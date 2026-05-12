from __future__ import annotations

import re
import pytest

from app.services.path_reconstruction_service import FORBIDDEN_PHRASES, SAFE_SUMMARY, _safe_summary_check


FORBIDDEN_WORDING = list(FORBIDDEN_PHRASES) + [
    "guilty",
    "confirmed criminal",
    "identity confirmed",
    "suspect confirmed",
]

ALLOWED_SAFE_WORDING = [
    "possible subject",
    "possible movement path",
    "candidate route",
    "investigative hypothesis",
    "operator review required",
    "evidence-backed hypothesis",
    "possible identity match",
]


@pytest.mark.parametrize("phrase", FORBIDDEN_WORDING)
def test_forbidden_phrase_blocked(phrase):
    result = _safe_summary_check(f"The {phrase} was found at the scene.")
    assert result == SAFE_SUMMARY, f"Expected SAFE_SUMMARY for phrase: {phrase}"


@pytest.mark.parametrize("phrase", ALLOWED_SAFE_WORDING)
def test_safe_phrase_passes(phrase):
    text = f"Analysis identified a {phrase} for operator review."
    result = _safe_summary_check(text)
    assert result == text


def test_safe_summary_contains_no_forbidden():
    lower = SAFE_SUMMARY.lower()
    for phrase in FORBIDDEN_WORDING:
        assert phrase not in lower


def test_investigation_model_safe_summary_default():
    from app.models.investigation_models import PathHypothesis, InvestigationSubjectRef
    hyp = PathHypothesis(
        hypothesis_id="hyp_test",
        subject_ref=InvestigationSubjectRef(type="manual", ref_id="ref_1"),
    )
    lower = hyp.safe_summary.lower()
    for phrase in FORBIDDEN_WORDING:
        assert phrase not in lower
