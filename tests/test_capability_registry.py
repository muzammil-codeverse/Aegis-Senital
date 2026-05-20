from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.capability_routes import router as capability_router
from app.core.capabilities import (
    CapabilityRegistry,
    CapabilityState,
    aggregate_capability_health,
    refresh_capability_status,
    register_default_capabilities,
)
from app.core.capabilities.registry import get_capability_registry


def test_default_capabilities_register_required_phase_one_ids():
    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    ids = {record.descriptor.id for record in registry.list()}

    assert "backend_api" in ids
    assert "uploaded_video_pipeline" in ids
    assert "drone_simulation" in ids
    assert "identity_reid" in ids
    assert "llm_osint" in ids
    assert len(ids) >= 31


def test_capability_states_serialize_as_api_safe_strings():
    registry = CapabilityRegistry()
    register_default_capabilities(registry)

    payload = registry.get("uploaded_video_pipeline").to_api_dict()

    assert payload["state"] == "COLD"
    assert payload["runtime_status"]["state"] == "COLD"
    assert payload["descriptor"]["category"] == "VIDEO_INTELLIGENCE"


def test_summary_counts_states_correctly():
    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    registry.mark_faulted("drone_simulation", "simulator unavailable")
    registry.mark_degraded("llm_osint", "provider credentials missing")
    registry.mark_ready("uploaded_video_pipeline", "pipeline checked")

    summary = aggregate_capability_health(registry.list())

    assert summary["faulted"] == 1
    assert summary["degraded"] == 1
    assert "drone_simulation" in summary["faulted_capabilities"]
    assert "uploaded_video_pipeline" in summary["ready_capabilities"]


def test_marking_faulted_degraded_ready_updates_runtime_status():
    registry = CapabilityRegistry()
    register_default_capabilities(registry)

    faulted = registry.mark_faulted("open_vocab_detection", "adapter missing")
    assert faulted.runtime_status.state == CapabilityState.FAULTED
    assert faulted.runtime_status.last_error == "adapter missing"

    degraded = registry.mark_degraded("open_vocab_detection", "model path not configured")
    assert degraded.runtime_status.state == CapabilityState.DEGRADED
    assert degraded.runtime_status.state_reason == "model path not configured"

    ready = registry.mark_ready("open_vocab_detection", "lightweight check passed")
    assert ready.runtime_status.state == CapabilityState.READY
    assert ready.runtime_status.last_error is None


def test_lightweight_check_does_not_warm_heavy_capability():
    registry = CapabilityRegistry()
    register_default_capabilities(registry)

    checked = refresh_capability_status(registry, "drone_simulation")

    assert checked.runtime_status.state in {CapabilityState.COLD, CapabilityState.DEGRADED}
    assert "managed activation" in checked.runtime_status.state_reason.lower()


def test_unknown_capability_route_returns_404(monkeypatch):
    monkeypatch.setattr("app.api.security_dependencies.auth_required", lambda: False)
    get_capability_registry().clear()
    app = FastAPI()
    app.include_router(capability_router)

    response = TestClient(app).get("/api/capabilities/not_registered")

    assert response.status_code == 404
    assert "not_registered" in response.json()["detail"]
