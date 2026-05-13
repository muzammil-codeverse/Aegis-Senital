from pathlib import Path

from scripts.configure_drone_multicamera_settings import _build_settings


ROOT = Path(__file__).resolve().parents[1]


def test_phase54_multicamera_settings_contains_required_cameras():
    settings = _build_settings("city_demo")
    drone = settings["Vehicles"]["Drone1"]
    cameras = drone["Cameras"]
    required = {"front_center", "front_left", "front_right", "downward", "rear"}
    assert required.issubset(set(cameras.keys()))


def test_phase54_multicamera_settings_has_expected_resolution_and_fov():
    settings = _build_settings("city_demo")
    capture = settings["Vehicles"]["Drone1"]["Cameras"]["front_center"]["CaptureSettings"][0]
    downward = settings["Vehicles"]["Drone1"]["Cameras"]["downward"]["CaptureSettings"][0]
    assert capture["Width"] == 1280
    assert capture["Height"] == 720
    assert capture["FOV_Degrees"] == 90
    assert downward["FOV_Degrees"] in {100, 110}


def test_phase54_multicamera_script_mentions_backup_behavior():
    text = (ROOT / "scripts" / "configure_drone_multicamera_settings.py").read_text(encoding="utf-8")
    assert "settings.backup." in text
    assert "settings.json" in text
