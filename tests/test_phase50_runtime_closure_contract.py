from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def test_final_demo_readiness_checklist_exists() -> None:
    assert _path("docs", "fyp_evidence", "final_demo_readiness_checklist.md").exists()


def test_production_readiness_matrix_exists() -> None:
    assert _path("docs", "fyp_evidence", "production_readiness_matrix.md").exists()


def test_final_capability_summary_exists() -> None:
    assert _path("docs", "fyp_evidence", "final_system_capability_summary.md").exists()


def test_final_known_limitations_exists() -> None:
    assert _path("docs", "fyp_evidence", "final_known_limitations.md").exists()


def test_final_demo_validation_script_exists() -> None:
    assert _path("scripts", "run_final_demo_validation.py").exists()


def test_model_asset_smoke_script_exists() -> None:
    assert _path("scripts", "smoke_all_model_assets.py").exists()


def test_backend_runtime_smoke_script_exists() -> None:
    assert _path("scripts", "smoke_backend_runtime.py").exists()


def test_final_demo_validation_prefers_project_venv() -> None:
    source = _path("scripts", "run_final_demo_validation.py").read_text(encoding="utf-8")
    assert '.venv" / "Scripts" / "python.exe"' in source


def test_validate_runtime_references_critical_config_files() -> None:
    source = _path("scripts", "validate_runtime.py").read_text(encoding="utf-8")
    required = [
        "configs/runtime/security.yaml",
        "configs/runtime/deployment.yaml",
        "configs/runtime/dependency_policy.yaml",
        "configs/runtime/model_governance.yaml",
        "configs/runtime/drone_simulation.yaml",
        "configs/runtime/drone_mission.yaml",
    ]
    for item in required:
        assert item in source


def test_dependency_manager_uses_ultralytics_for_segmentation_runtime() -> None:
    source = _path("ml", "runtime", "dependency_manager.py").read_text(encoding="utf-8")
    assert 'from ultralytics import SAM' in source
    assert 'importlib.import_module("sam2")' not in source


def test_frontend_guardrail_scripts_exist() -> None:
    assert _path("scripts", "check_frontend_safe_wording.py").exists()
    assert _path("scripts", "check_frontend_accessibility_static.py").exists()
    assert _path("scripts", "check_frontend_bundle_budget.py").exists()
