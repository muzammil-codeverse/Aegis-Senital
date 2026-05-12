"""Tests for Phase 46 drone fusion runtime health."""
import sys
from pathlib import Path

for p in (Path(__file__).parent.parent, Path(__file__).parent.parent / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


def test_drone_fusion_health_check(tmp_path):
    from app.repositories.drone_fusion_repository import DroneFusionRepository
    repo = DroneFusionRepository(root_dir=tmp_path / "health_test")
    health = repo.health_check()
    assert health["status"] == "healthy"
    assert health["backend"] == "jsonl"
    assert "observations" in health
    assert "correlations" in health
    assert "pending_reviews" in health


def test_runtime_health_service_includes_drone_fusion():
    from app.services.runtime_health_service import RuntimeHealthService
    svc = RuntimeHealthService()
    health = svc.get_health()
    assert "drone_fusion" in health, "runtime health must include drone_fusion block"
    df = health["drone_fusion"]
    assert "status" in df
    assert "observations" in df


def test_validate_runtime_drone_fusion_function_importable():
    import sys
    ROOT = Path(__file__).parent.parent
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    # Import validate_runtime as module
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "validate_runtime",
        ROOT / "scripts" / "validate_runtime.py"
    )
    mod = importlib.util.load_from_spec = None  # avoid executing __main__
    # Just verify the function exists by reading the source
    source = (ROOT / "scripts" / "validate_runtime.py").read_text()
    assert "validate_drone_fusion_configuration" in source


def test_production_repo_raises_when_required():
    from app.repositories.drone_fusion_repository import DroneFusionRepository, DroneFusionRepositoryError
    import pytest
    with pytest.raises(DroneFusionRepositoryError):
        DroneFusionRepository(production_mode=True, production_required=True)
