from app.models.osint_models import CaseEnrichmentSummaryRequest, CaseExternalSource


def test_osint_source_model_normalizes_metadata_and_labels():
    source = CaseExternalSource(
        case_id="case_123",
        source_type="EXTERNAL_LINK",
        title="Manual Source",
        source_reliability="HIGH",
        metadata={"count": 2, "unsafe": object()},
    )

    assert source.source_type == "external_link"
    assert source.source_reliability == "high"
    assert source.metadata["count"] == 2
    assert isinstance(source.metadata["unsafe"], str)
    assert source.analyst_provided is True
    assert source.requires_review is True


def test_enrichment_summary_request_trims_operator_instructions():
    request = CaseEnrichmentSummaryRequest(
        source_ids="src_1",
        operator_instructions="  focus on timeline relevance  ",
        escalate=True,
    )

    assert request.source_ids == ["src_1"]
    assert request.operator_instructions == "focus on timeline relevance"
    assert request.escalate is True
