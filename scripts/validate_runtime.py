#!/usr/bin/env python3
"""
Aegis Sentinel runtime validation script.
Validates config files, storage paths, secrets, and optional services.
Exits nonzero only for required failures.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def check(name: str, ok: bool, detail: str = "", required: bool = True) -> dict:
    status = "PASS" if ok else ("FAIL" if required else "WARN")
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return {"name": name, "ok": ok, "required": required, "status": status}


def validate():
    print("Aegis Sentinel — Runtime Validation")
    print("=" * 50)

    results = []
    required_failures = []

    # Config files
    print("\n[Config Files]")
    for cfg in [
        "configs/runtime/open_vocab.yaml",
        "configs/runtime/security.yaml",
        "configs/runtime/deployment.yaml",
    ]:
        exists = (ROOT / cfg).exists()
        r = check(cfg, exists, required=True)
        results.append(r)
        if not exists:
            required_failures.append(cfg)

    # Storage paths
    print("\n[Storage Paths]")
    for path_str in ["storage", "storage/open_vocab", "models", "backend/output"]:
        path = ROOT / path_str
        path.mkdir(parents=True, exist_ok=True)
        writable = os.access(str(path), os.W_OK)
        r = check(path_str, writable, "" if writable else "not writable", required=True)
        results.append(r)
        if not writable:
            required_failures.append(path_str)

    # JWT Secret
    print("\n[Security]")
    secret = os.environ.get("AEGIS_JWT_SECRET", "")
    app_env = os.environ.get("APP_ENV", "dev")
    default_secret = "change-this-in-production-use-a-long-random-string"
    secret_ok = bool(secret) and secret != default_secret
    secret_required = app_env == "production"
    r = check(
        "AEGIS_JWT_SECRET",
        secret_ok,
        "set" if secret_ok else ("not set or default" + (" (OK in dev)" if not secret_required else "")),
        required=secret_required,
    )
    results.append(r)
    if not secret_ok and secret_required:
        required_failures.append("AEGIS_JWT_SECRET")

    # Open-vocab model
    print("\n[Open-Vocab Model]")
    model_path = os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
    allow_download = os.environ.get("AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD", "false").lower() == "true"
    if model_path:
        path_exists = Path(model_path).exists()
        r = check(
            "AEGIS_OPEN_VOCAB_MODEL_PATH",
            path_exists,
            model_path if path_exists else f"path not found: {model_path}",
            required=False,
        )
    else:
        r = check(
            "AEGIS_OPEN_VOCAB_MODEL_PATH",
            False,
            "not set — scanner will be unavailable (degraded OK)",
            required=False,
        )
    results.append(r)
    r = check(
        "AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD",
        True,
        "enabled" if allow_download else "disabled (safe default)",
        required=False,
    )
    results.append(r)

    # GPU check
    print("\n[GPU]")
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        r = check(
            "CUDA",
            has_cuda,
            ("available: " + torch.cuda.get_device_name(0)) if has_cuda else "not available — CPU mode",
            required=False,
        )
    except ImportError:
        r = check("CUDA", False, "torch not installed — GPU check skipped", required=False)
    results.append(r)

    # Database
    print("\n[Optional Services]")
    dsn = os.environ.get("POSTGRES_DSN", "")
    r = check("POSTGRES_DSN", bool(dsn), "configured" if dsn else "not set (optional)", required=False)
    results.append(r)
    redis_url = os.environ.get("REDIS_URL", "")
    r = check("REDIS_URL", bool(redis_url), "configured" if redis_url else "not set (optional)", required=False)
    results.append(r)

    # Summary
    print("\n" + "=" * 50)
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")

    if required_failures:
        print(f"\nRequired failures ({len(required_failures)}):")
        for f in required_failures:
            print(f"  - {f}")
        print("\nFAILED — fix required issues before deploying.")
        sys.exit(1)
    else:
        print("\nPASSED — all required checks OK.")
        sys.exit(0)


if __name__ == "__main__":
    validate()
