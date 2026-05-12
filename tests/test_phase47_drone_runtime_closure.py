from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase47_drone_runtime_closure_files_exist():
    required = [
        ROOT / "scripts" / "launch_blocks_runtime.py",
        ROOT / "scripts" / "verify_drone_sim_dependencies.py",
        ROOT / "scripts" / "verify_drone_sim_runtime.py",
        ROOT / "scripts" / "smoke_cosys_airsim_runtime.py",
        ROOT / "scripts" / "smoke_drone_simulation_pipeline.py",
        ROOT / "scripts" / "smoke_drone_mission.py",
        ROOT / "scripts" / "smoke_drone_fixed_camera_fusion.py",
        ROOT / "docs" / "fyp_evidence" / "drone_runtime_closure_report.md",
    ]
    for path in required:
        assert path.exists(), str(path)


def test_phase47_drone_runtime_closure_report_contains_validation_markers():
    report = (ROOT / "docs" / "fyp_evidence" / "drone_runtime_closure_report.md").read_text(encoding="utf-8")
    expected = [
      "Dependency strict check: PASS",
      "Runtime strict validation: PASS",
      "Drone pipeline smoke: PASS",
      "Mission smoke: PASS",
      "Fusion live smoke: PASS",
      "EXCEPTION_ACCESS_VIOLATION",
      "Blocks.exe -windowed -ResX=640 -ResY=480",
    ]
    for marker in expected:
        assert marker in report
