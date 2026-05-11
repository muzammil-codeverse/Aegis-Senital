from __future__ import annotations

import pytest

from inference.identity.liveness_adapter import LivenessAdapter, LivenessProviderMissingError


def test_liveness_disabled_shows_disabled_status():
    cfg = {"liveness": {"enabled": False, "provider": "none"}}
    adapter = LivenessAdapter(config=cfg, profile="production")
    h = adapter.get_health()
    assert h["status"] == "disabled"
    assert h["enabled"] is False


def test_liveness_enabled_without_provider_fails_production_readiness():
    cfg = {"liveness": {"enabled": True, "provider": "none", "fail_if_enabled_without_provider": True}}
    adapter = LivenessAdapter(config=cfg, profile="production")
    with pytest.raises(LivenessProviderMissingError):
        adapter.assert_ready()


def test_liveness_enabled_without_provider_warns_in_development():
    cfg = {"liveness": {"enabled": True, "provider": "pending", "fail_if_enabled_without_provider": False}}
    adapter = LivenessAdapter(config=cfg, profile="development")
    adapter.assert_ready()
