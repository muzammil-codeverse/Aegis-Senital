from app.repositories.case_repository import JsonlCaseRepository
from app.services import case_service as case_service_module
from app.services.case_service import CaseService


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {"jsonl_dir": str(tmp_path / "cases")},
            "auto_create": {"enabled": False},
            "deduplication": {"enabled": False},
        }
    }


def test_case_timeline_orders_items_ascending(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    case = service.create_case({"title": "Possible anomaly incident"}, actor="operator")
    service.add_evidence(case.case_id, {"evidence_type": "event", "title": "Event linked", "timestamp": "2026-05-10T10:00:01+00:00"}, actor="operator")
    service.add_note(case.case_id, {"note": "Operator note."}, actor="operator")
    service.assign_case(case.case_id, "alice", actor="operator")

    timeline = service.get_timeline(case.case_id)
    timestamps = [item.timestamp for item in timeline]
    assert timestamps == sorted(timestamps)
    assert any(item.type == "note" for item in timeline)
    assert any("Assignment" in item.title or item.type == "audit" for item in timeline)


def test_case_timeline_ids_are_stable_between_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    case = service.create_case({"title": "Possible anomaly incident"}, actor="operator")
    service.add_evidence(case.case_id, {"evidence_type": "event", "title": "Event linked"}, actor="operator")

    first = service.get_timeline(case.case_id)
    second = service.get_timeline(case.case_id)

    assert [item.timeline_id for item in first] == [item.timeline_id for item in second]
