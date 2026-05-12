#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.env_loader import load_project_env
from app.core.secret_safety import secret_presence_label

DEFAULT_JWT_SECRET = "change-this-in-production-use-a-long-random-string"


def _load_llm_config() -> dict:
    path = ROOT / "configs" / "runtime" / "llm.yaml"
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _openai_required() -> bool:
    payload = _load_llm_config()
    llm_cfg = payload.get("llm", payload)
    if not isinstance(llm_cfg, dict):
        return False
    if not bool(llm_cfg.get("enabled", False)):
        return False
    provider_name = str(llm_cfg.get("provider") or llm_cfg.get("default_provider") or "local_stub").strip().lower()
    if provider_name != "openai":
        return False
    providers = dict(llm_cfg.get("providers") or {})
    openai_cfg = dict(providers.get("openai") or {})
    return bool(openai_cfg.get("enabled", True))


def build_secret_report(profile: str) -> list[dict[str, object]]:
    jwt_secret = str(os.getenv("AEGIS_JWT_SECRET") or "")
    postgres_dsn = str(os.getenv("POSTGRES_DSN") or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("DB_URL") or "")
    redis_url = str(os.getenv("REDIS_URL") or "")
    openai_key = str(os.getenv("OPENAI_API_KEY") or "")

    report = [
        {
            "name": "AEGIS_JWT_SECRET",
            "required": profile == "production",
            "present": bool(jwt_secret.strip()) and jwt_secret != DEFAULT_JWT_SECRET,
            "detail": "PRESENT" if bool(jwt_secret.strip()) else "MISSING",
            "valid": bool(jwt_secret.strip()) and jwt_secret != DEFAULT_JWT_SECRET and len(jwt_secret) >= 32,
            "failure": "must be present, non-default, and at least 32 characters",
        },
        {
            "name": "POSTGRES_DSN",
            "required": profile == "production",
            "present": bool(postgres_dsn.strip()),
            "detail": secret_presence_label(postgres_dsn),
            "valid": bool(postgres_dsn.strip()) and postgres_dsn.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://", "postgresql+asyncpg://")),
            "failure": "must be present and use a PostgreSQL DSN",
        },
        {
            "name": "REDIS_URL",
            "required": profile == "production",
            "present": bool(redis_url.strip()),
            "detail": secret_presence_label(redis_url),
            "valid": bool(redis_url.strip()) and redis_url.startswith(("redis://", "rediss://")),
            "failure": "must be present and use a Redis URL",
        },
    ]

    if _openai_required():
        report.append(
            {
                "name": "OPENAI_API_KEY",
                "required": profile == "production",
                "present": bool(openai_key.strip()),
                "detail": secret_presence_label(openai_key),
                "valid": bool(openai_key.strip()),
                "failure": "must be present when the OpenAI provider is enabled",
            }
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production secret presence without printing secret values.")
    parser.add_argument("--profile", choices=("development", "production"), default="production")
    args = parser.parse_args()

    load_project_env()
    failures: list[str] = []
    for item in build_secret_report(args.profile):
        required = bool(item["required"])
        valid = bool(item["valid"])
        detail = str(item["detail"])
        if valid:
            print(f"[PASS] {item['name']}: {detail}")
            continue
        status = "FAIL" if required else "WARN"
        print(f"[{status}] {item['name']}: {detail}")
        if required:
            failures.append(f"{item['name']} {item['failure']}")

    if failures:
        print("Production secret validation failed.")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Production secret validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
