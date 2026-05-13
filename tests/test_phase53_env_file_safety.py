"""
Phase 53 — Environment File Safety Tests

Verifies that sensitive environment files are gitignored and that
env_loader correctly handles profile-based file loading.
"""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_env_production_local_is_gitignored():
    gitignore_path = PROJECT_ROOT / ".gitignore"
    assert gitignore_path.exists(), ".gitignore must exist"
    content = gitignore_path.read_text(encoding="utf-8")
    assert "*.local" in content or ".env.production.local" in content, (
        ".env.production.local must be covered by .gitignore"
    )


def test_no_secrets_in_committed_env_example_file():
    example_path = PROJECT_ROOT / ".env.docker.example"
    if not example_path.exists():
        return
    content = example_path.read_text(encoding="utf-8")
    assert "sk-proj" not in content, "OPENAI_API_KEY must not appear in .env.docker.example"
    assert "sk-" not in content or "sk-YOUR" in content or "sk-proj-..." in content or content.count("sk-") == 0, (
        "No real API key patterns in .env.docker.example"
    )


def test_env_loader_candidate_paths_include_production_local(monkeypatch):
    monkeypatch.setenv("AEGIS_ENV", "production")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("AEGIS_PROFILE", raising=False)

    from app.core import env_loader
    candidates = env_loader._candidate_paths()
    candidate_names = [p.name for p in candidates]
    assert ".env.production.local" in candidate_names


def test_env_loader_candidate_paths_include_dev_local(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.delenv("AEGIS_PROFILE", raising=False)

    from app.core import env_loader
    candidates = env_loader._candidate_paths()
    candidate_names = [p.name for p in candidates]
    assert ".env.development.local" in candidate_names


def test_env_loader_always_includes_base_env(monkeypatch):
    monkeypatch.delenv("AEGIS_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("AEGIS_PROFILE", raising=False)

    from app.core import env_loader
    candidates = env_loader._candidate_paths()
    candidate_names = [p.name for p in candidates]
    assert ".env" in candidate_names


def test_storage_and_models_dirs_not_committed():
    gitignore_path = PROJECT_ROOT / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    for pattern in ("storage/", "models/"):
        assert any(pattern in line or pattern.rstrip("/") in line for line in lines), (
            f"'{pattern}' must appear in .gitignore"
        )
    env_local_covered = any(
        "*.local" in line or ".env.production.local" in line
        for line in lines
    )
    assert env_local_covered, ".env.production.local must be covered by .gitignore (via *.local or explicit entry)"
