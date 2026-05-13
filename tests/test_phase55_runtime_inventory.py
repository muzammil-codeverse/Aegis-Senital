from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase55_runtime_inventory_scripts_exist():
    required = [
        ROOT / "scripts" / "download_airsim_city_environment.py",
        ROOT / "scripts" / "verify_drone_runtime_inventory.py",
        ROOT / "scripts" / "launch_city_drone_runtime.py",
        ROOT / "scripts" / "smoke_city_drone_runtime.py",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase55_runtime_inventory_contract_markers():
    verify_text = _read(ROOT / "scripts" / "verify_drone_runtime_inventory.py")
    smoke_text = _read(ROOT / "scripts" / "smoke_city_drone_runtime.py")
    launch_text = _read(ROOT / "scripts" / "launch_city_drone_runtime.py")

    assert "--require-city" in verify_text
    assert "Blocks" in verify_text
    assert "AirSimNH" in verify_text
    assert "CityEnviron" in verify_text
    assert "fallback_used" in smoke_text
    assert "runtime_type" in launch_text
