"""Tests for Phase 46 drone fusion config."""
from pathlib import Path
import yaml


CONFIG_PATH = Path(__file__).parent.parent / "configs" / "runtime" / "drone_fusion.yaml"


def test_config_exists():
    assert CONFIG_PATH.exists(), "drone_fusion.yaml must exist"


def test_config_parseable():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(cfg, dict)


def test_config_has_drone_fusion_key():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert "drone_fusion" in cfg


def test_safety_config_present():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    safety = cfg["drone_fusion"]["safety"]
    assert safety["safe_wording_required"] is True
    assert safety["prohibit_guilt_language"] is True
    assert safety["prohibit_identity_confirmation"] is True


def test_identity_prohibit_auto_confirmation():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    identity = cfg["drone_fusion"]["identity"]
    assert identity["prohibit_auto_confirmation"] is True
    assert identity["require_operator_review"] is True


def test_correlation_thresholds():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    corr = cfg["drone_fusion"]["correlation"]
    assert corr["min_fusion_confidence"] >= 0.0
    assert corr["max_time_delta_seconds"] > 0


def test_scoring_weights_sum_to_one():
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    s = cfg["drone_fusion"]["scoring"]
    total = (s["time_weight"] + s["geo_weight"] + s["appearance_weight"]
             + s["event_type_weight"] + s["mission_context_weight"])
    assert abs(total - 1.0) < 0.01, f"weights sum to {total}, expected 1.0"
