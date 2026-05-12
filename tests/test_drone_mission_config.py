"""Tests for configs/runtime/drone_mission.yaml (Phase 45)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "configs" / "runtime" / "drone_mission.yaml"


@pytest.fixture(scope="module")
def cfg():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


@pytest.fixture(scope="module")
def mission_cfg(cfg):
    return cfg.get("drone_mission", {})


def test_config_exists():
    assert CONFIG_PATH.exists(), "drone_mission.yaml must exist"


def test_enabled(mission_cfg):
    assert mission_cfg.get("enabled") is True


def test_provider(mission_cfg):
    assert mission_cfg.get("provider") == "cosys_airsim"


def test_safety_simulated_only(mission_cfg):
    assert mission_cfg.get("safety", {}).get("simulated_only") is True


def test_safety_require_operator_start(mission_cfg):
    assert mission_cfg.get("safety", {}).get("require_operator_start") is True


def test_safety_prohibit_real_world_claims(mission_cfg):
    assert mission_cfg.get("safety", {}).get("prohibit_real_world_claims") is True


def test_safety_require_mission_audit(mission_cfg):
    assert mission_cfg.get("safety", {}).get("require_mission_audit") is True


def test_mission_min_max_waypoints(mission_cfg):
    m = mission_cfg.get("mission", {})
    assert m.get("min_waypoints", 0) >= 2
    assert m.get("max_waypoints", 0) >= 10


def test_storage_keys(mission_cfg):
    storage = mission_cfg.get("storage", {})
    assert "root_dir" in storage
    assert "telemetry_dir" in storage
    assert "reports_dir" in storage


def test_replay_enabled(mission_cfg):
    replay = mission_cfg.get("replay", {})
    assert replay.get("enabled") is True
