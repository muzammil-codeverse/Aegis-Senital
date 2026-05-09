#!/usr/bin/env python3
"""Aegis Sentinel runtime validation script.

Validates config files, storage paths, secrets, optional services, and
profile-appropriate Python dependencies.

Usage:
  python scripts/validate_runtime.py
  python scripts/validate_runtime.py --profile development
  python scripts/validate_runtime.py --profile production
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
POLICY_PATH = ROOT / "configs" / "runtime" / "dependency_policy.yaml"


def check(name: str, ok: bool, detail: str = "", required: bool = True) -> dict:
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return {"name": name, "ok": ok, "required": required, "status": status}


def _try_import(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Profile-based dependency validation
# ---------------------------------------------------------------------------

def load_policy() -> dict:
    with open(POLICY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_dependencies(profile: str) -> list[dict]:
    policy = load_policy()
    profiles = policy.get("profiles", {})
    if profile not in profiles:
        print(f"  [WARN] Unknown profile '{profile}' — skipping dependency checks")
        return []

    prof = profiles[profile]
    results: list[dict] = []

    required_entries: list[dict] = prof.get("required", [])
    optional_entries: list[dict] = prof.get("optional", [])
    conditional_entries: list[dict] = prof.get("required_if_env", [])

    print(f"\n[Dependencies — profile: {profile}]")

    for entry in required_entries:
        ok = _try_import(entry["module"])
        hint = "" if ok else f"install: {entry.get('install_hint', '')}"
        r = check(entry["label"], ok, hint, required=True)
        results.append(r)

    for entry in optional_entries:
        ok = _try_import(entry["module"])
        detail = ""
        if not ok:
            detail = entry.get("reason", "")
        r = check(entry["label"], ok, detail, required=False)
        results.append(r)

    for entry in conditional_entries:
        env_val = os.environ.get(entry["env_var"], "")
        if not env_val:
            continue
        ok = _try_import(entry["module"])
        hint = "" if ok else f"{entry['env_var']} is set but module is missing"
        r = check(entry["label"], ok, hint, required=True)
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Core validation (unchanged from original — profile-independent)
# ---------------------------------------------------------------------------

def validate(profile: str) -> None:
    print("Aegis Sentinel — Runtime Validation")
    print("=" * 50)

    all_results: list[dict] = []
    required_failures: list[str] = []

    def _record(r: dict) -> None:
        all_results.append(r)
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])

    # Config files
    print("\n[Config Files]")
    for cfg in [
        "configs/runtime/open_vocab.yaml",
        "configs/runtime/security.yaml",
        "configs/runtime/deployment.yaml",
        "configs/runtime/dependency_policy.yaml",
    ]:
        exists = (ROOT / cfg).exists()
        _record(check(cfg, exists, required=True))

    # Storage paths
    print("\n[Storage Paths]")
    for path_str in ["storage", "storage/open_vocab", "models", "backend/output"]:
        path = ROOT / path_str
        path.mkdir(parents=True, exist_ok=True)
        writable = os.access(str(path), os.W_OK)
        _record(check(path_str, writable, "" if writable else "not writable", required=True))

    # Model registry
    print("\n[Model Registry]")
    registry_path = ROOT / "models" / "registry.json"
    registry_exists = registry_path.exists()
    _record(check("models/registry.json", registry_exists, required=True))
    if registry_exists:
        import json
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            for model_type in ("weapon", "phone"):
                entry = registry.get(model_type, {})
                model_path = ROOT / entry.get("path", "MISSING")
                exists = model_path.exists()
                _record(check(
                    f"models/{model_type}/current.pt",
                    exists,
                    str(model_path) if not exists else "",
                    required=True,
                ))
        except Exception as exc:
            _record(check("registry.json parseable", False, str(exc), required=True))

    # JWT Secret
    print("\n[Security]")
    secret = os.environ.get("AEGIS_JWT_SECRET", "")
    app_env = os.environ.get("APP_ENV", "dev")
    default_secret = "change-this-in-production-use-a-long-random-string"
    secret_ok = bool(secret) and secret != default_secret
    secret_required = app_env == "production" or profile == "production"
    _record(check(
        "AEGIS_JWT_SECRET",
        secret_ok,
        "set" if secret_ok else ("not set or default" + (" (OK in dev)" if not secret_required else "")),
        required=secret_required,
    ))

    # Open-vocab model
    print("\n[Open-Vocab Model]")
    model_path = os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
    allow_download = os.environ.get("AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD", "false").lower() == "true"
    if model_path:
        path_exists = Path(model_path).exists()
        _record(check(
            "AEGIS_OPEN_VOCAB_MODEL_PATH",
            path_exists,
            model_path if path_exists else f"path not found: {model_path}",
            required=False,
        ))
    else:
        _record(check(
            "AEGIS_OPEN_VOCAB_MODEL_PATH",
            False,
            "not set — scanner will be unavailable (degraded OK)",
            required=False,
        ))
    _record(check(
        "AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD",
        True,
        "enabled" if allow_download else "disabled (safe default)",
        required=False,
    ))

    # GPU check
    print("\n[GPU]")
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        _record(check(
            "CUDA",
            has_cuda,
            ("available: " + torch.cuda.get_device_name(0)) if has_cuda else "not available — CPU mode",
            required=False,
        ))
    except ImportError:
        _record(check("CUDA", False, "torch not installed — GPU check skipped", required=False))

    # Optional services
    print("\n[Optional Services]")
    dsn = os.environ.get("POSTGRES_DSN", "")
    _record(check("POSTGRES_DSN", bool(dsn), "configured" if dsn else "not set (optional)", required=False))
    redis_url = os.environ.get("REDIS_URL", "")
    _record(check("REDIS_URL", bool(redis_url), "configured" if redis_url else "not set (optional)", required=False))

    # Profile-based dependency checks
    dep_results = validate_dependencies(profile)
    for r in dep_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(dep_results)

    # Summary
    print("\n" + "=" * 50)
    passed = sum(1 for r in all_results if r["ok"])
    total = len(all_results)
    print(f"Profile: {profile}  |  Results: {passed}/{total} checks passed")

    if required_failures:
        print(f"\nRequired failures ({len(required_failures)}):")
        for f in required_failures:
            print(f"  - {f}")
        print("\nFAILED — fix required issues before deploying.")
        sys.exit(1)
    else:
        print("\nPASSED — all required checks OK.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--profile",
        choices=("development", "production"),
        default="development",
        help="Dependency enforcement profile (default: development)",
    )
    args = parser.parse_args()
    validate(profile=args.profile)


if __name__ == "__main__":
    main()
