from __future__ import annotations

import pytest

from inference.identity.liveness_adapter import LivenessAdapter, LivenessProviderMissingError


def test_liveness_disabled_reports_disabled():
    adapter = LivenessAdapter(config={"liveness": {"enabled": False}})
    health = adapter.get_health()
    assert health["status"] == "disabled"


def test_liveness_enabled_missing_provider_fails_in_production():
    adapter = LivenessAdapter(
        config={"liveness": {"enabled": True, "provider": "pending", "fail_if_enabled_missing": True}},
        profile="production",
    )
    with pytest.raises(LivenessProviderMissingError):
        adapter.assert_ready()
