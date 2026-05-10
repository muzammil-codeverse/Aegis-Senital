import pytest

from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "evidence": {"max_items_per_case": 10},
            "auto_create": {
                "enabled": True,
                "min_severity": "high",
                "event_types": [
                    "weapon_detected",
                    "open_vocab_scan_result",
                    "anomaly_event",
                    "identity_match",
                    "restricted_zone_intrusion",
                ],
            },
            "deduplication": {
                "enabled": True,
                "window_seconds": 300,
                "same_camera_merge": True,
                "same_track_merge": True,
                "same_event_type_merge": True,
            },
        }
    }


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    repo = JsonlCaseRepository(config=_config(tmp_path))
    return CaseService(repository=repo, config=_config(tmp_path))


def test_case_service_create_update_assign_and_notes(service):
    case = service.create_case({"title": "Possible restricted-zone incident", "severity": "high", "priority": "high"}, actor="operator")
    updated = service.update_case(case.case_id, {"status": "investigating"}, actor="operator")
    assigned = service.assign_case(case.case_id, "alice", actor="operator", reason="Primary reviewer")
    note = service.add_note(case.case_id, {"note": "Operator review in progress."}, actor="operator")

    assert updated.status == "investigating"
    assert assigned.assigned_to == "alice"
    assert service.list_notes(case.case_id)[0].note_id == note.note_id


def test_case_service_rejects_invalid_transition(service):
    case = service.create_case({"title": "Possible anomaly incident"}, actor="operator")
    service.close_case(case.case_id, actor="supervisor", reason="Resolved")
    with pytest.raises(ValueError):
        service.dismiss_case(case.case_id, actor="supervisor", reason="Invalid after resolved")


def test_case_service_handles_missing_evidence_file(service):
    case = service.create_case({"title": "Possible evidence workflow incident"}, actor="operator")
    evidence = service.add_evidence(
        case.case_id,
        {
            "evidence_type": "attachment",
            "storage_uri": "C:/missing/file.jpg",
            "title": "Missing snapshot",
        },
        actor="operator",
    )
    assert evidence.integrity_status == "missing_file"
    assert evidence.metadata["missing_evidence"] is True
