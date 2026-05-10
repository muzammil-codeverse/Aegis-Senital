from app.models.case_models import CaseEvidence, CaseRecord
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


def test_case_auto_create_and_deduplicate_related_events(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))

    first = service.create_or_attach_from_event({
        "event_type": "WEAPON_THREAT",
        "event_id": "evt_1",
        "severity": "high",
        "camera_ids": ["cam_01"],
        "track_ids": ["track_12"],
        "timestamp": "2026-05-10T10:00:00+00:00",
    })
    second = service.create_or_attach_from_event({
        "event_type": "WEAPON_THREAT",
        "event_id": "evt_2",
        "severity": "critical",
        "camera_ids": ["cam_01"],
        "track_ids": ["track_12"],
        "timestamp": "2026-05-10T10:01:00+00:00",
    })

    assert isinstance(first, CaseRecord)
    assert isinstance(second, CaseEvidence)
    cases = service.list_cases({})
    assert len(cases) == 1
    assert set(cases[0].source_event_ids) == {"evt_1", "evt_2"}


def test_case_auto_create_rejects_low_severity_event(tmp_path, monkeypatch):
    monkeypatch.setattr(case_service_module, "_CASE_SERVICE_SUBSCRIBED", True)
    service = CaseService(repository=JsonlCaseRepository(config=_config(tmp_path)), config=_config(tmp_path))
    result = service.create_or_attach_from_event({
        "event_type": "WEAPON_THREAT",
        "event_id": "evt_low",
        "severity": "low",
        "camera_ids": ["cam_01"],
        "track_ids": ["track_01"],
        "timestamp": "2026-05-10T10:00:00+00:00",
    })
    assert result is None
