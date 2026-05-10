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


def test_case_export_json_and_markdown_include_caveats(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    case = service.create_case({"title": "Possible weapon-related event", "severity": "high", "priority": "high"}, actor="operator")
    service.add_note(case.case_id, {"note": "Operator review pending."}, actor="operator")

    exported_json = service.export_case(case.case_id, format="json", actor="operator")
    exported_md = service.export_case(case.case_id, format="markdown", actor="operator")

    assert "operator_review_caveat" in exported_json.content
    assert "This report is an automated decision-support draft based on available system evidence." in exported_md.content
