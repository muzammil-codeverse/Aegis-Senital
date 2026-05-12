import inference.config_runtime as runtime_config
import inference.identity.runtime_config as identity_runtime_config
from app.services.runtime_health_service import RuntimeHealthService


def test_runtime_health_includes_drone_simulation_block(monkeypatch):
    monkeypatch.setattr(
        RuntimeHealthService,
        "_check_drone_simulation",
        lambda self: {
            "enabled": True,
            "provider": "cosys_airsim",
            "status": "disconnected",
            "simulator_connected": False,
            "telemetry_available": False,
            "frame_available": False,
            "active_session": False,
            "last_error": "runtime offline",
        },
    )

    health = RuntimeHealthService(config={}).get_health(include_sensitive=False)

    assert "drone_simulation" in health["checks"]
    assert health["checks"]["drone_simulation"]["status"] == "disconnected"


def test_runtime_readiness_fails_in_production_when_drone_runtime_is_required(monkeypatch):
    def fake_load(name: str):
        if name == "drone_simulation":
            return {
                "drone_simulation": {
                    "enabled": True,
                    "connection": {"require_runtime_in_production": True},
                }
            }
        return {}

    monkeypatch.setattr(RuntimeHealthService, "_check_database", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_redis", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_gpu", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_storage", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_security", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_open_vocab", lambda self: {"status": "ok", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_segmentation", lambda self: {"status": "healthy", "detail": "ok"})
    monkeypatch.setattr(RuntimeHealthService, "_check_identity", lambda self: {"status": "healthy", "calibration": {}})
    monkeypatch.setattr(RuntimeHealthService, "_check_case_management", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_llm", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_osint_enrichment", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_streaming", lambda self: {"enabled": False, "status": "disabled", "missing_dependencies": []})
    monkeypatch.setattr(RuntimeHealthService, "_check_analytics", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_uploaded_video", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_gis", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_investigation", lambda self: {"enabled": False, "status": "disabled"})
    monkeypatch.setattr(RuntimeHealthService, "_check_persistence", lambda self: {"enabled": False, "status": "disabled", "failures": []})
    monkeypatch.setattr(
        RuntimeHealthService,
        "_check_drone_simulation",
        lambda self: {
            "enabled": True,
            "provider": "cosys_airsim",
            "status": "disconnected",
            "simulator_connected": False,
            "telemetry_available": False,
            "frame_available": False,
            "active_session": False,
            "last_error": "runtime offline",
        },
    )
    monkeypatch.setattr(RuntimeHealthService, "_production_mode", staticmethod(lambda: True))
    monkeypatch.setattr(runtime_config, "load_runtime_config", fake_load)
    monkeypatch.setattr(identity_runtime_config, "load_identity_config", lambda: {"enabled": False, "liveness": {}, "calibration": {}})

    readiness = RuntimeHealthService(config={}).is_ready()

    assert readiness["ready"] is False
    assert any("drone_simulation" in failure for failure in readiness["failures"])
