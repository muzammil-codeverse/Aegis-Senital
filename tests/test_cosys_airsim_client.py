from types import SimpleNamespace

from app.services.drone.cosys_airsim_client import CosysAirSimClient


def _client() -> CosysAirSimClient:
    return CosysAirSimClient(
        host="127.0.0.1",
        port=41451,
        vehicle_name="Drone1",
        camera_name="front_center",
        timeout_seconds=1.0,
        default_home={"latitude": 30.1575, "longitude": 71.5249, "altitude_meters": 40},
    )


def test_missing_client_module_reports_clear_error(monkeypatch):
    client = _client()
    client._last_error = "cosysairsim is not installed. Install the prepared Python client first."
    monkeypatch.setattr(client, "_load_client_module", lambda: None)

    status = client.connect()

    assert status.status == "disconnected"
    assert status.connected is False
    assert "cosysairsim" in (status.last_error or "").lower()


def test_simulator_not_running_returns_disconnected_without_fake_telemetry(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_load_client_module", lambda: SimpleNamespace())
    monkeypatch.setattr(client, "_port_open", lambda: False)

    status = client.connect()
    telemetry = client.get_telemetry()

    assert status.status == "disconnected"
    assert "not reachable" in (status.last_error or "").lower()
    assert telemetry.status == "disconnected"
    assert telemetry.latitude is None
    assert telemetry.longitude is None


def test_named_vehicle_rpc_falls_back_to_default_vehicle(monkeypatch):
    client = _client()
    calls = {"state": 0, "images": 0}

    def fake_state(*args, vehicle_name=None):
        calls["state"] += 1
        if vehicle_name == "Drone1":
            raise RuntimeError("Vehicle API for 'Drone1' is not available.")
        position = SimpleNamespace(x_val=1.0, y_val=2.0, z_val=-3.0)
        velocity = SimpleNamespace(x_val=0.1, y_val=0.2, z_val=0.3)
        orientation = SimpleNamespace(x_val=0.0, y_val=0.0, z_val=0.0, w_val=1.0)
        kinematics = SimpleNamespace(
            position=position,
            linear_velocity=velocity,
            orientation=orientation,
        )
        gps = SimpleNamespace(latitude=30.1575, longitude=71.5249, altitude=40.0)
        return SimpleNamespace(kinematics_estimated=kinematics, gps_location=gps)

    def fake_images(requests, vehicle_name=None):
        calls["images"] += 1
        if vehicle_name == "Drone1":
            raise RuntimeError("Retry connection over the limit")
        response = SimpleNamespace(
            width=2,
            height=2,
            image_data_uint8=b"\x00\x00\x00" * 4,
        )
        return [response]

    client._client_module = SimpleNamespace(
        ImageRequest=lambda *args: args,
        ImageType=SimpleNamespace(Scene=0, Segmentation=5, DepthPlanar=1),
    )
    client._client = SimpleNamespace(
        getMultirotorState=fake_state,
        simGetImages=fake_images,
    )
    client._connected = True

    telemetry = client.get_telemetry()
    frame = client.get_frame()

    assert telemetry.status == "connected"
    assert telemetry.latitude == 30.1575
    assert frame.frame_available is True
    assert frame.width == 2
    assert frame.height == 2
    assert client._supports_named_vehicle_calls is False
    assert calls["state"] == 2
    assert calls["images"] == 1


def test_constructor_uses_runtime_env_defaults(monkeypatch):
    monkeypatch.setenv("AEGIS_AIRSIM_HOST", "192.0.2.5")
    monkeypatch.setenv("AEGIS_AIRSIM_PORT", "45555")
    monkeypatch.setenv("AEGIS_AIRSIM_VEHICLE", "FallbackDrone")
    monkeypatch.setenv("AEGIS_AIRSIM_CAMERA", "downward")

    client = CosysAirSimClient()

    assert client.host == "192.0.2.5"
    assert client.port == 45555
    assert client.vehicle_name == "FallbackDrone"
    assert client.camera_name == "downward"
