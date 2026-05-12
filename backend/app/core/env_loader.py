from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
_PROFILE_ALIASES = {
    "dev": "development",
    "development": "development",
    "prod": "production",
    "production": "production",
    "test": "test",
    "testing": "test",
}


def _normalized_profiles() -> list[str]:
    profiles: list[str] = []
    for raw_value in (
        os.getenv("AEGIS_PROFILE"),
        os.getenv("AEGIS_ENV"),
        os.getenv("APP_ENV"),
    ):
        value = str(raw_value or "").strip().lower()
        if not value:
            continue
        normalized = _PROFILE_ALIASES.get(value, value)
        if normalized not in profiles:
            profiles.append(normalized)
    return profiles


def _candidate_paths() -> list[Path]:
    candidates = [
        PROJECT_ROOT / ".env",
        BACKEND_ROOT / ".env",
        PROJECT_ROOT / ".env.local",
        BACKEND_ROOT / ".env.local",
    ]
    for profile in _normalized_profiles():
        candidates.extend(
            [
                PROJECT_ROOT / f".env.{profile}",
                BACKEND_ROOT / f".env.{profile}",
                PROJECT_ROOT / f".env.{profile}.local",
                BACKEND_ROOT / f".env.{profile}.local",
            ]
        )

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


@lru_cache(maxsize=1)
def load_project_env(*, override: bool = False) -> tuple[str, ...]:
    try:
        from dotenv import load_dotenv
    except Exception:
        return ()

    loaded: list[str] = []
    for candidate in _candidate_paths():
        if not candidate.exists():
            continue
        load_dotenv(candidate, override=override)
        loaded.append(str(candidate))
    return tuple(loaded)
