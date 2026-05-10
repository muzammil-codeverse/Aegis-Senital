from app.models.case_models import CaseEvidence, CaseRecord


def test_case_record_defaults_and_closed_state():
    case = CaseRecord(title="Possible restricted-zone incident", severity="high", priority="high")
    assert case.status == "open"
    assert case.requires_review is True
    assert case.review_status == "pending"
    assert case.closed_at is None


def test_case_record_coerces_lists_and_closed_at_for_resolved():
    case = CaseRecord(
        title="Possible anomaly incident",
        status="resolved",
        source_event_ids="evt_1",
        camera_ids="cam_01",
        track_ids="track_12",
        tags="requires-review",
    )
    assert case.source_event_ids == ["evt_1"]
    assert case.camera_ids == ["cam_01"]
    assert case.track_ids == ["track_12"]
    assert case.tags == ["requires-review"]
    assert case.closed_at is not None


def test_case_evidence_defaults():
    evidence = CaseEvidence(case_id="case_1", evidence_type="event", metadata={"camera_id": "cam_01"})
    assert evidence.integrity_status == "not_applicable"
    assert evidence.metadata["camera_id"] == "cam_01"
