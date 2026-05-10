from app.services.analytics_service import AnalyticsService


class _RiskRepository:
    enabled = True
    storage_backend = "jsonl"

    def get_events(self, time_range, filters=None):
        del time_range, filters
        return [
            {
                "event_id": "evt-1",
                "event_type": "possible_incident",
                "severity": "critical",
                "timestamp": "2026-05-10T01:00:00+00:00",
                "camera_id": "cam_01",
                "camera_ids": ["cam_01"],
            },
            {
                "event_id": "evt-2",
                "event_type": "anomaly_motion",
                "severity": "high",
                "timestamp": "2026-05-10T02:00:00+00:00",
                "camera_id": "cam_01",
                "camera_ids": ["cam_01"],
            },
        ]

    def get_cases(self, time_range, filters=None):
        del time_range, filters
        return [{"case_id": "case-1", "status": "open", "camera_ids": ["cam_01"], "requires_review": True}]

    def get_stream_health(self, time_range, filters=None):
        del time_range, filters
        return [{"camera_id": "cam_01", "state": "running", "health": {"status": "healthy"}, "stats": {}}]

    def get_identity_matches(self, time_range, filters=None):
        del time_range, filters
        return [{"camera_id": "cam_01", "operator_review_required": True}]

    def get_model_metrics(self, time_range, filters=None):
        del time_range, filters
        return []

    def get_source_statuses(self):
        return {"events": "healthy"}

    def probe_sources(self):
        return {"events": "healthy"}

    def get_last_error(self):
        return None


def test_camera_risk_scoring_is_deterministic():
    service = AnalyticsService(
        repository=_RiskRepository(),
        config={
            "analytics": {
                "enabled": True,
                "cache": {"enabled": False},
                "risk_scoring": {
                    "severity_weights": {"low": 1, "medium": 3, "high": 7, "critical": 12},
                    "case_weight": 5,
                    "unresolved_case_multiplier": 1.5,
                    "repeated_camera_multiplier": 1.2,
                },
            }
        },
    )

    risk = service.get_camera_risk(None, {})

    assert len(risk) == 1
    assert risk[0].camera_id == "cam_01"
    assert risk[0].risk_score == 50.4
    assert risk[0].review_priority == "high"
