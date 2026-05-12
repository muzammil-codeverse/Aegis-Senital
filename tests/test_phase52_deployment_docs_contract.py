"""
Phase 52 — Deployment Documentation Contract Tests

Verifies that all deployment and FYP evidence documents required by Phase 52 exist
and contain expected content sections.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


DEPLOYMENT_DIR = ROOT / "docs" / "deployment"
FYP_EVIDENCE_DIR = ROOT / "docs" / "fyp_evidence"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    assert path.exists(), f"Required document missing: {path}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# DOCKER_PRODUCTION_RUNBOOK.md
# ---------------------------------------------------------------------------

class TestDockerProductionRunbook:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(DEPLOYMENT_DIR / "DOCKER_PRODUCTION_RUNBOOK.md")

    def test_file_exists(self):
        assert len(self._content) > 100

    def test_contains_backend_service_section(self):
        assert "backend" in self._content.lower()

    def test_contains_frontend_service_section(self):
        assert "frontend" in self._content.lower()

    def test_contains_postgres_section(self):
        assert "postgres" in self._content.lower()

    def test_contains_redis_section(self):
        assert "redis" in self._content.lower()

    def test_contains_gpu_section(self):
        assert "gpu" in self._content.lower() or "cuda" in self._content.lower()

    def test_contains_environment_variables_section(self):
        assert "AEGIS_JWT_SECRET" in self._content
        assert "POSTGRES_DSN" in self._content
        assert "REDIS_URL" in self._content

    def test_contains_health_check_endpoints(self):
        assert "/api/system/health" in self._content or "readiness" in self._content.lower()

    def test_contains_model_path_mounts(self):
        assert "models" in self._content

    def test_contains_volume_mounts(self):
        assert "volume" in self._content.lower() or "volumes" in self._content.lower()

    def test_contains_health_checks(self):
        assert "health" in self._content.lower()


# ---------------------------------------------------------------------------
# PRODUCTION_DEPLOYMENT_CHECKLIST.md
# ---------------------------------------------------------------------------

class TestProductionDeploymentChecklist:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(DEPLOYMENT_DIR / "PRODUCTION_DEPLOYMENT_CHECKLIST.md")

    def test_file_exists(self):
        assert len(self._content) > 100

    def test_contains_secrets_section(self):
        assert "AEGIS_JWT_SECRET" in self._content

    def test_contains_database_bootstrap_section(self):
        assert "bootstrap" in self._content.lower() or "PostgreSQL" in self._content

    def test_contains_redis_startup_section(self):
        assert "redis" in self._content.lower()

    def test_contains_model_assets_section(self):
        assert "model" in self._content.lower()

    def test_contains_frontend_build_section(self):
        assert "frontend" in self._content.lower() or "npm run build" in self._content

    def test_contains_backend_health_section(self):
        assert "health" in self._content.lower()

    def test_contains_production_runtime_validation(self):
        assert "validate_runtime" in self._content

    def test_contains_drone_simulation_optionality(self):
        assert "drone" in self._content.lower()

    def test_contains_openai_verification(self):
        assert "openai" in self._content.lower() or "OPENAI_API_KEY" in self._content

    def test_contains_governance_evidence(self):
        assert "governance" in self._content.lower() or "anomaly" in self._content.lower()

    def test_contains_external_blockers_table(self):
        assert "external" in self._content.lower() or "blocker" in self._content.lower()


# ---------------------------------------------------------------------------
# final_fyp_demo_runbook.md
# ---------------------------------------------------------------------------

class TestFinalFYPDemoRunbook:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(FYP_EVIDENCE_DIR / "final_fyp_demo_runbook.md")

    def test_file_exists(self):
        assert len(self._content) > 100

    def test_contains_backend_start(self):
        assert "backend" in self._content.lower()

    def test_contains_frontend_start(self):
        assert "frontend" in self._content.lower()

    def test_contains_dashboard(self):
        assert "dashboard" in self._content.lower()

    def test_contains_uploaded_video_workflow(self):
        assert "video" in self._content.lower() or "upload" in self._content.lower()

    def test_contains_gis_map(self):
        assert "gis" in self._content.lower() or "map" in self._content.lower()

    def test_contains_drone(self):
        assert "drone" in self._content.lower()

    def test_contains_case_evidence(self):
        assert "case" in self._content.lower() or "evidence" in self._content.lower()

    def test_contains_llm_report(self):
        assert "llm" in self._content.lower() or "report" in self._content.lower()

    def test_contains_model_governance(self):
        assert "governance" in self._content.lower() or "model" in self._content.lower()

    def test_contains_analytics(self):
        assert "analytics" in self._content.lower()

    def test_contains_validation_evidence(self):
        assert "validation" in self._content.lower() or "evidence" in self._content.lower()


# ---------------------------------------------------------------------------
# docs/fyp_evidence/README.md index
# ---------------------------------------------------------------------------

class TestFYPEvidenceReadme:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(FYP_EVIDENCE_DIR / "README.md")

    def test_file_exists(self):
        assert len(self._content) > 50

    def test_indexes_final_demo_readiness_checklist(self):
        assert "final_demo_readiness_checklist" in self._content

    def test_indexes_production_readiness_matrix(self):
        assert "production_readiness_matrix" in self._content

    def test_indexes_final_system_capability_summary(self):
        assert "final_system_capability_summary" in self._content

    def test_indexes_final_known_limitations(self):
        assert "final_known_limitations" in self._content

    def test_indexes_drone_runtime_closure_report(self):
        assert "drone_runtime_closure_report" in self._content

    def test_indexes_e2e_validation_summary(self):
        assert "e2e_validation_summary" in self._content

    def test_indexes_phase52_audit(self):
        assert "phase52" in self._content.lower()

    def test_indexes_final_fyp_demo_runbook(self):
        assert "final_fyp_demo_runbook" in self._content


# ---------------------------------------------------------------------------
# phase52_error_closure_audit.md
# ---------------------------------------------------------------------------

class TestPhase52ErrorClosureAudit:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(FYP_EVIDENCE_DIR / "phase52_error_closure_audit.md")

    def test_file_exists(self):
        assert len(self._content) > 100

    def test_contains_error_classification(self):
        assert "external" in self._content.lower() or "blocker" in self._content.lower()

    def test_contains_production_blockers_section(self):
        assert "production" in self._content.lower()

    def test_no_hidden_failures(self):
        # Must not claim everything passed when production services are missing
        # The doc must acknowledge external blockers
        honest_terms = ["missing", "not configured", "external", "blocker", "required"]
        found = any(t in self._content.lower() for t in honest_terms)
        assert found, "Audit doc appears to hide failures — must acknowledge external blockers"


# ---------------------------------------------------------------------------
# repository_hygiene_report.md
# ---------------------------------------------------------------------------

class TestRepositoryHygieneReport:
    @pytest.fixture(autouse=True)
    def content(self):
        self._content = _read(FYP_EVIDENCE_DIR / "repository_hygiene_report.md")

    def test_file_exists(self):
        assert len(self._content) > 50

    def test_covers_inference_drone(self):
        assert "inference" in self._content.lower() or "drone" in self._content.lower()

    def test_covers_untracked_files(self):
        assert "untracked" in self._content.lower() or "tracked" in self._content.lower()

    def test_covers_phase51_scripts(self):
        assert "phase51" in self._content.lower() or "bootstrap" in self._content.lower() or \
               "validate_production" in self._content.lower()
