from scripts.configure_drone_multicamera_settings import _build_settings


def test_phase55_multicamera_required_views_present():
    settings = _build_settings("city_demo")
    cameras = settings["Vehicles"]["Drone1"]["Cameras"]
    required = {"front_center", "front_left", "front_right", "downward", "rear"}
    assert required.issubset(set(cameras.keys()))


def test_phase55_multicamera_resolution_and_fov():
    settings = _build_settings("city_demo")
    front = settings["Vehicles"]["Drone1"]["Cameras"]["front_center"]["CaptureSettings"][0]
    down = settings["Vehicles"]["Drone1"]["Cameras"]["downward"]["CaptureSettings"][0]
    assert front["Width"] == 1280
    assert front["Height"] == 720
    assert front["FOV_Degrees"] == 90
    assert down["FOV_Degrees"] == 110
