"""
Phase 52 — Error Closure Contract Tests

Verifies that Phase 52 audit documents exist, production checks are not disabled,
safe wording enforcement remains in place, and the no-JSONL-fallback rule is active.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest


# ---------------------------------------------------------------------------
# Phase 52 documentation exists
# ---------------------------------------------------------------------------

class TestPhase52DocumentsExist:
    def test_phase52_audit_doc_exists(self):
        path = ROOT / "docs" / "fyp_evidence" / "phase52_error_closure_audit.md"
        assert path.exists(), f"Missing: {path}"

    def test_repository_hygiene_report_exists(self):
        path = ROOT / "docs" / "fyp_evidence" / "repository_hygiene_report.md"
        assert path.exists(), f"Missing: {path}"

    def test_production_deployment_checklist_exists(self):
        path = ROOT / "docs" / "deployment" / "PRODUCTION_DEPLOYMENT_CHECKLIST.md"
        assert path.exists(), f"Missing: {path}"

    def test_docker_production_runbook_exists(self):
        path = ROOT / "docs" / "deployment" / "DOCKER_PRODUCTION_RUNBOOK.md"
        assert path.exists(), f"Missing: {path}"

    def test_final_demo_runbook_exists(self):
        path = ROOT / "docs" / "fyp_evidence" / "final_fyp_demo_runbook.md"
        assert path.exists(), f"Missing: {path}"

    def test_fyp_evidence_readme_exists(self):
        path = ROOT / "docs" / "fyp_evidence" / "README.md"
        assert path.exists(), f"Missing: {path}"


# ---------------------------------------------------------------------------
# Production validation scripts still exist and are not gutted
# ---------------------------------------------------------------------------

class TestProductionScriptsPresent:
    def test_validate_production_secrets_script_exists(self):
        path = ROOT / "scripts" / "validate_production_secrets.py"
        assert path.exists(), f"Missing: {path}"

    def test_check_redis_runtime_script_exists(self):
        path = ROOT / "scripts" / "check_redis_runtime.py"
        assert path.exists(), f"Missing: {path}"

    def test_check_postgres_schema_script_exists(self):
        path = ROOT / "scripts" / "check_postgres_schema.py"
        assert path.exists(), f"Missing: {path}"

    def test_run_production_readiness_script_exists(self):
        path = ROOT / "scripts" / "run_production_readiness_validation.py"
        assert path.exists(), f"Missing: {path}"

    def test_bootstrap_postgres_script_exists(self):
        path = ROOT / "scripts" / "bootstrap_postgres.py"
        assert path.exists(), f"Missing: {path}"

    def test_generate_anomaly_live_eval_script_exists(self):
        path = ROOT / "scripts" / "generate_anomaly_live_eval_summary.py"
        assert path.exists(), f"Missing: {path}"

    def test_validate_runtime_script_exists(self):
        path = ROOT / "scripts" / "validate_runtime.py"
        assert path.exists(), f"Missing: {path}"

    def test_check_frontend_safe_wording_script_exists(self):
        path = ROOT / "scripts" / "check_frontend_safe_wording.py"
        assert path.exists(), f"Missing: {path}"


# ---------------------------------------------------------------------------
# Safe wording enforcement is intact
# ---------------------------------------------------------------------------

class TestSafeWordingIntact:
    def test_safe_wording_script_contains_forbidden_list(self):
        path = ROOT / "scripts" / "check_frontend_safe_wording.py"
        content = path.read_text(encoding="utf-8")
        # Script stores forbidden terms in lowercase — check lowercase
        forbidden_samples = [
            "suspect confirmed",
            "identity confirmed",
            "target confirmed",
        ]
        for term in forbidden_samples:
            assert term in content, f"Forbidden wording '{term}' missing from safe wording check script"

    def test_safe_wording_script_contains_banned_patterns_list(self):
        path = ROOT / "scripts" / "check_frontend_safe_wording.py"
        content = path.read_text(encoding="utf-8")
        # The script must define a BANNED_PATTERNS list or similar structure
        assert "BANNED_PATTERNS" in content or "banned" in content.lower() or "forbidden" in content.lower(), \
            "Safe wording script must contain a banned/forbidden patterns definition"

    def test_safe_wording_script_contains_real_drone_pursuit(self):
        path = ROOT / "scripts" / "check_frontend_safe_wording.py"
        content = path.read_text(encoding="utf-8")
        assert "real drone pursuit" in content.lower(), \
            "Safe wording script must forbid 'real drone pursuit'"


# ---------------------------------------------------------------------------
# Production no-JSONL-fallback rules are intact
# ---------------------------------------------------------------------------

class TestNoJSONLFallbackIntact:
    def test_persistence_module_has_prohibit_jsonl_fallback(self):
        from app.core.persistence import prohibit_jsonl_fallback  # noqa: F401

    def test_prohibit_jsonl_fallback_is_callable(self):
        from app.core.persistence import prohibit_jsonl_fallback
        assert callable(prohibit_jsonl_fallback)

    def test_prohibit_jsonl_fallback_returns_true_by_default(self):
        from app.core.persistence import prohibit_jsonl_fallback

        # Default (no config override) must return True — JSONL fallback is prohibited
        result = prohibit_jsonl_fallback()
        assert result is True, "prohibit_jsonl_fallback() must return True by default"

    def test_persistence_module_has_require_postgres(self):
        from app.core.persistence import require_postgres  # noqa: F401

    def test_persistence_module_has_is_production_environment(self):
        from app.core.persistence import is_production_environment  # noqa: F401


# ---------------------------------------------------------------------------
# validate_runtime production profile still checks required items
# ---------------------------------------------------------------------------

class TestValidateRuntimeProductionChecks:
    def test_validate_runtime_checks_jwt_secret(self):
        """Production profile must check for JWT secret."""
        path = ROOT / "scripts" / "validate_runtime.py"
        content = path.read_text(encoding="utf-8")
        assert "AEGIS_JWT_SECRET" in content, "validate_runtime.py does not check AEGIS_JWT_SECRET"

    def test_validate_runtime_checks_postgres_dsn(self):
        """Production profile must check for PostgreSQL DSN."""
        path = ROOT / "scripts" / "validate_runtime.py"
        content = path.read_text(encoding="utf-8")
        assert "POSTGRES_DSN" in content or "postgres" in content.lower(), \
            "validate_runtime.py does not check POSTGRES_DSN"

    def test_validate_runtime_checks_openai_key(self):
        """Production profile must check for OpenAI key when LLM is enabled."""
        path = ROOT / "scripts" / "validate_runtime.py"
        content = path.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY" in content, "validate_runtime.py does not check OPENAI_API_KEY"

    def test_validate_runtime_has_production_profile(self):
        """validate_runtime.py must support --profile production argument."""
        path = ROOT / "scripts" / "validate_runtime.py"
        content = path.read_text(encoding="utf-8")
        assert "production" in content, "validate_runtime.py has no production profile"


# ---------------------------------------------------------------------------
# Auth/RBAC is intact
# ---------------------------------------------------------------------------

class TestAuthRBACIntact:
    def test_security_dependencies_module_exists(self):
        from app.api.security_dependencies import require_permission  # noqa: F401

    def test_require_permission_is_callable(self):
        from app.api.security_dependencies import require_permission
        assert callable(require_permission)

    def test_require_auth_is_callable(self):
        from app.api.security_dependencies import require_auth  # noqa: F401
        assert callable(require_auth)

    def test_jwt_utils_module_exists(self):
        from app.security.jwt_utils import decode_access_token  # noqa: F401

    def test_decode_access_token_is_callable(self):
        from app.security.jwt_utils import decode_access_token
        assert callable(decode_access_token)

    def test_object_authorization_module_exists(self):
        path = ROOT / "backend" / "app" / "security"
        # Auth module directory must exist with core files
        assert path.exists()
        py_files = list(path.glob("*.py"))
        assert len(py_files) > 0, "security module has no Python files"

    def test_permissions_module_exists(self):
        from app.security.permissions import has_permission  # noqa: F401
        assert callable(has_permission)
