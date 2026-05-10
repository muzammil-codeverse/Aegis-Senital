from app.models.case_models import CaseAuditLog, CaseEvidence, CaseExport, CaseNote, CaseRecord
from app.repositories.case_repository import JsonlCaseRepository


def _config(tmp_path):
    return {
        "case_management": {
            "enabled": True,
            "storage": {
                "jsonl_dir": str(tmp_path / "cases"),
            },
        }
    }


def test_jsonl_repository_crud_and_append_only_records(tmp_path):
    repo = JsonlCaseRepository(config=_config(tmp_path))
    case = repo.create_case(CaseRecord(title="Possible restricted-zone incident", severity="high", priority="high"))
    assert repo.get_case(case.case_id) is not None

    updated = repo.update_case(case.case_id, {"status": "investigating", "updated_at": case.updated_at})
    assert updated.status == "investigating"
    assert repo.list_cases({"status": "investigating"})[0].case_id == case.case_id

    archived = repo.delete_or_archive_case(case.case_id)
    assert archived.status == "archived"


def test_jsonl_repository_evidence_notes_audit_and_reports(tmp_path):
    repo = JsonlCaseRepository(config=_config(tmp_path))
    case = repo.create_case(CaseRecord(title="Possible anomaly incident"))
    evidence = repo.add_evidence(CaseEvidence(case_id=case.case_id, evidence_type="event", source_event_id="evt_1"))
    note = repo.add_note(CaseNote(case_id=case.case_id, note="Operator review pending."))
    audit = repo.add_audit_log(CaseAuditLog(case_id=case.case_id, action="case_created"))
    export = repo.add_report(CaseExport(case_id=case.case_id, format="json", report_type="draft_case_report", content="{}"))

    assert repo.list_evidence(case.case_id)[0].evidence_id == evidence.evidence_id
    assert repo.list_notes(case.case_id)[0].note_id == note.note_id
    assert repo.list_audit_logs(case.case_id)[0].audit_id == audit.audit_id
    assert repo.list_reports(case.case_id)[0].export_id == export.export_id
    assert repo.list_reports(case.case_id)[0].report_type == "draft_case_report"
