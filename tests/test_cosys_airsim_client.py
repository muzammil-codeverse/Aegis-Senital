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
