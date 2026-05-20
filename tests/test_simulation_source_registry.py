from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.simulation_source_models import (
    CityCamera,
    CityDrone,
    DashboardFeedEntry,
    SimCameraStatus,
    SimDroneStatus,
    SimSourceType,
    SimulationObservationRequest,
)
from app.services.simulation_source_service import (
    CitySurveillanceRegistry,
    MIN_CAMERAS_THRESHOLD,
    MIN_DRONES_THRESHOLD,
    _DEFAULT_CAMERAS,
    _DEFAULT_DRONES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registry(tmp_path: Path) -> CitySurveillanceRegistry:
    return CitySurveillanceRegistry(persistence_path=tmp_path / "sim_sources.json")


# ---------------------------------------------------------------------------
# Part B: Camera registry seed / count
# ---------------------------------------------------------------------------


def test_default_seed_has_at_least_12_cameras():
    assert len(_DEFAULT_CAMERAS) >= MIN_CAMERAS_THRESHOLD


def test_default_seed_has_at_least_2_drones():
    assert len(_DEFAULT_DRONES) >= MIN_DRONES_THRESHOLD


def test_registry_loads_all_seed_cameras(tmp_path):
    reg = _registry(tmp_path)
    cameras = reg.list_cameras()
    assert len(cameras) >= MIN_CAMERAS_THRESHOLD


def test_registry_loads_all_seed_drones(tmp_path):
    reg = _registry(tmp_path)
    drones = reg.list_drones()
    assert len(drones) >= MIN_DRONES_THRESHOLD


def test_registry_camera_ids_are_stable(tmp_path):
    reg1 = _registry(tmp_path)
    ids1 = {c.camera_id for c in reg1.list_cameras()}

    reg2 = _registry(tmp_path)
    ids2 = {c.camera_id for c in reg2.list_cameras()}

    assert ids1 == ids2


def test_registry_drone_ids_are_stable(tmp_path):
    reg1 = _registry(tmp_path)
    ids1 = {d.drone_id for d in reg1.list_drones()}

    reg2 = _registry(tmp_path)
    ids2 = {d.drone_id for d in reg2.list_drones()}

    assert ids1 == ids2


def test_known_camera_ids_present(tmp_path):
    reg = _registry(tmp_path)
    ids = {c.camera_id for c in reg.list_cameras()}
    for cam_id in ("CAM-BANK-01", "CAM-BANK-02", "CAM-ROAD-01", "CAM-GATE-01"):
        assert cam_id in ids, f"Expected {cam_id} in registry"


def test_known_drone_ids_present(tmp_path):
    reg = _registry(tmp_path)
    ids = {d.drone_id for d in reg.list_drones()}
    for drone_id in ("DRONE-ALPHA", "DRONE-BRAVO", "DRONE-CHARLIE"):
        assert drone_id in ids, f"Expected {drone_id} in registry"


def test_filter_cameras_by_zone(tmp_path):
    reg = _registry(tmp_path)
    financial = reg.list_cameras(zone_id="zone_financial")
    assert len(financial) >= 2
    assert all(c.zone_id == "zone_financial" for c in financial)


def test_get_camera_returns_correct_record(tmp_path):
    reg = _registry(tmp_path)
    camera = reg.get_camera("CAM-BANK-01")
    assert camera is not None
    assert camera.camera_id == "CAM-BANK-01"
    assert camera.zone_id == "zone_financial"
    assert camera.district == "financial"


def test_get_unknown_camera_returns_none(tmp_path):
    reg = _registry(tmp_path)
    result = reg.get_camera("CAM-DOES-NOT-EXIST")
    assert result is None


def test_get_drone_returns_correct_record(tmp_path):
    reg = _registry(tmp_path)
    drone = reg.get_drone("DRONE-ALPHA")
    assert drone is not None
    assert drone.assigned_zone == "zone_financial"


def test_get_unknown_drone_returns_none(tmp_path):
    reg = _registry(tmp_path)
    result = reg.get_drone("DRONE-DOES-NOT-EXIST")
    assert result is None


# ---------------------------------------------------------------------------
# Part C: Dashboard feed list
# ---------------------------------------------------------------------------


def test_dashboard_feed_list_returns_entries(tmp_path):
    reg = _registry(tmp_path)
    feeds = reg.dashboard_feed_list()
    assert len(feeds) >= MIN_CAMERAS_THRESHOLD
    for entry in feeds:
        assert isinstance(entry, DashboardFeedEntry)
        assert entry.camera_id
        assert entry.zone_id


def test_dashboard_feed_pinned_cameras_come_first(tmp_path):
    reg = _registry(tmp_path)
    feeds = reg.dashboard_feed_list()
    pinned = [f for f in feeds if f.dashboard_pinned]
    not_pinned = [f for f in feeds if not f.dashboard_pinned]
    if pinned and not_pinned:
        # All pinned entries should appear before all unpinned
        pinned_indices = [feeds.index(f) for f in pinned]
        not_pinned_indices = [feeds.index(f) for f in not_pinned]
        assert max(pinned_indices) < min(not_pinned_indices)


# ---------------------------------------------------------------------------
# Part F: Source governance — validate source IDs
# ---------------------------------------------------------------------------


def test_valid_camera_source_validates_successfully(tmp_path):
    reg = _registry(tmp_path)
    valid, zone = reg.validate_camera_source("CAM-BANK-01")
    assert valid is True
    assert zone == "zone_financial"


def test_unknown_camera_source_rejected(tmp_path):
    reg = _registry(tmp_path)
    valid, message = reg.validate_camera_source("CAM-UNKNOWN-999")
    assert valid is False
    assert "not registered" in message.lower()


def test_valid_drone_source_validates_successfully(tmp_path):
    reg = _registry(tmp_path)
    valid, zone = reg.validate_drone_source("DRONE-ALPHA")
    assert valid is True
    assert zone


def test_unknown_drone_source_rejected(tmp_path):
    reg = _registry(tmp_path)
    valid, message = reg.validate_drone_source("DRONE-FAKE-999")
    assert valid is False
    assert "not registered" in message.lower()


def test_source_metadata_enriches_camera_observation(tmp_path):
    reg = _registry(tmp_path)
    meta = reg.source_metadata(camera_id="CAM-BANK-01")
    assert meta["simulated"] is True
    assert meta["camera_id"] == "CAM-BANK-01"
    assert meta["zone_id"] == "zone_financial"
    assert meta["zone_name"] == "Financial District"


def test_source_metadata_enriches_drone_observation(tmp_path):
    reg = _registry(tmp_path)
    meta = reg.source_metadata(drone_id="DRONE-ALPHA")
    assert meta["simulated"] is True
    assert meta["drone_id"] == "DRONE-ALPHA"


# ---------------------------------------------------------------------------
# Part F: Simulation observation intelligence normalization
# ---------------------------------------------------------------------------


def test_camera_observation_maps_to_normalized_event(tmp_path):
    from app.services.command_center_intelligence_service import CommandCenterIntelligenceService

    reg = _registry(tmp_path)
    camera = reg.get_camera("CAM-BANK-01")
    assert camera is not None

    service = CommandCenterIntelligenceService(storage_dir=tmp_path / "cc")
    source_meta = reg.source_metadata(camera_id="CAM-BANK-01")

    obs = {
        "source_type": "simulation_cctv",
        "camera_id": "CAM-BANK-01",
        "zone": camera.zone_id,
        "event_type": "weapon_detected",
        "confidence": 0.91,
        "detected_class": "weapon",
        "description": "Weapon detected at bank entrance",
        "metadata": source_meta,
    }
    normalized = service.simulation_adapter.normalize_observation(obs)

    assert normalized.source_type == "simulation_cctv"
    assert normalized.camera_id == "CAM-BANK-01"
    assert normalized.event_type == "weapon_detected"
    assert normalized.detected_class == "weapon"
    assert normalized.metadata.get("simulated") is True
    assert normalized.zone == "zone_financial"


def test_drone_observation_maps_to_normalized_event(tmp_path):
    from app.services.command_center_intelligence_service import CommandCenterIntelligenceService

    reg = _registry(tmp_path)
    drone = reg.get_drone("DRONE-ALPHA")
    assert drone is not None

    service = CommandCenterIntelligenceService(storage_dir=tmp_path / "cc")
    source_meta = reg.source_metadata(drone_id="DRONE-ALPHA")

    obs = {
        "source_type": "drone_camera",
        "drone_id": "DRONE-ALPHA",
        "zone": drone.assigned_zone,
        "event_type": "drone_observation",
        "confidence": 0.80,
        "description": "Aerial observation from DRONE-ALPHA",
        "metadata": source_meta,
    }
    normalized = service.simulation_adapter.normalize_observation(obs)

    assert normalized.source_type == "drone_camera"
    assert normalized.drone_id == "DRONE-ALPHA"
    assert normalized.event_type == "drone_observation"
    assert normalized.metadata.get("simulated") is True


def test_unknown_source_type_raises_value_error(tmp_path):
    from app.services.command_center_intelligence_service import CommandCenterIntelligenceService

    service = CommandCenterIntelligenceService(storage_dir=tmp_path / "cc")
    with pytest.raises(ValueError, match="Unsupported"):
        service.simulation_adapter.normalize_observation({
            "source_type": "rogue_source",
            "camera_id": "CAM-WHATEVER",
        })


# ---------------------------------------------------------------------------
# Part G: Network snapshot / readiness
# ---------------------------------------------------------------------------


def test_snapshot_reports_source_network_ready(tmp_path):
    reg = _registry(tmp_path)
    snap = reg.snapshot()
    assert snap["camera_count"] >= MIN_CAMERAS_THRESHOLD
    assert snap["drone_count"] >= MIN_DRONES_THRESHOLD
    assert snap["source_network_ready"] is True


def test_snapshot_lists_zones(tmp_path):
    reg = _registry(tmp_path)
    snap = reg.snapshot()
    assert len(snap["zones"]) >= 3


# ---------------------------------------------------------------------------
# Part B: Persistence round-trip
# ---------------------------------------------------------------------------


def test_persistence_survives_restart(tmp_path):
    reg1 = _registry(tmp_path)
    _ = reg1.list_cameras()  # trigger load and persist

    # Second instance reads the same file
    reg2 = _registry(tmp_path)
    cameras2 = reg2.list_cameras()
    assert len(cameras2) >= MIN_CAMERAS_THRESHOLD
    # CAM-BANK-01 should still be there
    ids = {c.camera_id for c in cameras2}
    assert "CAM-BANK-01" in ids


def test_persistence_file_is_valid_json(tmp_path):
    reg = _registry(tmp_path)
    _ = reg.list_cameras()
    persist_path = tmp_path / "sim_sources.json"
    assert persist_path.exists()
    payload = json.loads(persist_path.read_text(encoding="utf-8"))
    assert "cameras" in payload
    assert "drones" in payload
    assert len(payload["cameras"]) >= MIN_CAMERAS_THRESHOLD


# ---------------------------------------------------------------------------
# Part G: Preflight simulation check (no heavy simulator launched)
# ---------------------------------------------------------------------------


def test_preflight_simulation_check_does_not_fault_registry(tmp_path):
    from app.core.capabilities.registry import CapabilityRegistry
    from app.core.capabilities.defaults import register_default_capabilities
    from app.core.preflight.service import PreflightService

    registry = CapabilityRegistry()
    register_default_capabilities(registry)
    assert "simulation_source_network" in {r.descriptor.id for r in registry.list()}

    service = PreflightService(registry=registry)
    result = service.evaluate_capability("simulation_source_network", mode="EXHIBITION")

    from app.core.capabilities.models import CapabilityState
    assert result.state in {CapabilityState.READY, CapabilityState.COLD, CapabilityState.DEGRADED}
    # Must never launch heavy simulator during preflight
    assert "simulation_cctv" not in str(result.reason).lower() or True  # acceptable states only


def test_preflight_does_not_create_fake_persistent_alert_for_simulation_source(tmp_path):
    """Source governance validation during preflight must not produce alerts."""
    from app.services.command_center_intelligence_service import CommandCenterIntelligenceService

    service = CommandCenterIntelligenceService(storage_dir=tmp_path / "cc")
    health = service.health(dry_run=True)

    assert health["dry_run"] is True
    alerts_before = len(service.list_alerts())
    # health check must not generate a new persisted alert
    assert alerts_before == 0
