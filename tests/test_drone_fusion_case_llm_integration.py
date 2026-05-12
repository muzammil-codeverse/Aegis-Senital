"""Tests for Phase 46 case/LLM fusion safety integration."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_llm_fusion_safety_context_defined():
    from app.services.llm_service import LLM_FUSION_SAFETY_CONTEXT
    assert "candidate relationships" in LLM_FUSION_SAFETY_CONTEXT.lower()
    assert "not confirmed identity" in LLM_FUSION_SAFETY_CONTEXT.lower()


def test_llm_prohibited_rewrites_include_fusion_phrases():
    from app.services.llm_service import PROHIBITED_REWRITES
    patterns = [r[0].pattern for r in PROHIBITED_REWRITES]
    assert any("suspect moved from camera" in p.lower() for p in patterns)
    assert any("target confirmed" in p.lower() for p in patterns)
    assert any("real drone pursuit" in p.lower() for p in patterns)


def test_case_timeline_service_importable():
    from app.services.case_timeline_service import CaseTimelineService
    assert CaseTimelineService is not None


def test_fusion_safety_model_safe_summary():
    from app.models.drone_fusion_models import FusionSummaryReport
    report = FusionSummaryReport()
    assert "operator review" in report.safe_summary.lower()


def test_fusion_model_rejects_forbidden_safe_summary():
    from app.models.drone_fusion_models import CrossSourceCorrelation, FusionConfidenceBreakdown
    import pydantic
    with pytest.raises((pydantic.ValidationError, ValueError)):
        CrossSourceCorrelation(
            primary_observation_id="a",
            matched_observation_id="b",
            source_pair=["fixed_camera", "drone_simulation"],
            confidence=0.6,
            confidence_breakdown=FusionConfidenceBreakdown(),
            safe_summary="confirmed suspect moved from camera to drone",
        )
