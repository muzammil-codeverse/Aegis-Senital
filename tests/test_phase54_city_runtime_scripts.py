from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase54_city_runtime_scripts_exist():
    required = [
        ROOT / "scripts" / "download_airsim_city_environment.py",
        ROOT / "scripts" / "launch_city_drone_runtime.py",
        ROOT / "scripts" / "smoke_city_drone_runtime.py",
        ROOT / "scripts" / "drone_runtime_catalog.py",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase54_city_runtime_scripts_have_fallback_logic():
    launch_text = _read(ROOT / "scripts" / "launch_city_drone_runtime.py")
    smoke_text = _read(ROOT / "scripts" / "smoke_city_drone_runtime.py")
    catalog_text = _read(ROOT / "scripts" / "drone_runtime_catalog.py")

    assert "CityEnviron" in launch_text
    assert "AirSimNH" in launch_text
    assert "Blocks" in launch_text
    assert "fallback_used" in smoke_text
    assert "runtime_inventory.json" in catalog_text
