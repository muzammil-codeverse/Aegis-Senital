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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def _get_nested(data: dict, path: str, default=None):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


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

    results.extend(validate_feature_dependencies(policy, profile))
    results.extend(validate_identity_feature_dependencies(policy, profile))

    return results


def validate_feature_dependencies(policy: dict, profile: str) -> list[dict]:
    results: list[dict] = []
    feature_cfg = policy.get("feature_dependencies", {}).get("segmentation", {})
    if not feature_cfg:
        return results

    print("\n[Feature Dependencies — segmentation]")
    config_path = ROOT / feature_cfg.get("config_path", "configs/runtime/segmentation.yaml")
    if not config_path.exists():
        required = profile == "production"
        results.append(check("segmentation config", False, str(config_path), required=required))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("segmentation config parseable", False, str(exc), required=True))
        return results

    enabled = bool(_get_nested(cfg, feature_cfg.get("enabled_path", "segmentation.enabled"), False))
    provider = str(_get_nested(cfg, feature_cfg.get("provider_path", "segmentation.provider"), "sam2")).lower()
    results.append(check("segmentation enabled", True, "enabled" if enabled else "disabled", required=False))
    if not enabled:
        return results
    if provider != "sam2":
        results.append(check("segmentation provider", False, f"unsupported provider: {provider}", required=profile == "production"))
        return results

    required = profile == "production"
    module = feature_cfg.get("module", "sam2")
    module_ok = _try_import(module)
    detail = "available" if module_ok else f"missing; install: {feature_cfg.get('install_hint', '')}"
    results.append(check(feature_cfg.get("label", "SAM2 segmentation"), module_ok, detail, required=required))

    checkpoint_value = _get_nested(
        cfg,
        "segmentation.sam2.checkpoint_path",
        feature_cfg.get("checkpoint_path", "models/segmentation/sam2/checkpoint.pt"),
    )
    model_config_value = _get_nested(
        cfg,
        "segmentation.sam2.model_config",
        feature_cfg.get("model_config", "configs/segmentation/sam2.yaml"),
    )
    checkpoint = ROOT / str(checkpoint_value)
    model_config = ROOT / str(model_config_value)
    results.append(check("SAM2 checkpoint", checkpoint.exists(), str(checkpoint), required=required))
    results.append(check("SAM2 model config", model_config.exists(), str(model_config), required=required))
    if profile == "development" and (not module_ok or not checkpoint.exists() or not model_config.exists()):
        results.append(check(
            "segmentation degraded mode",
            False,
            "segmentation enabled but SAM2 assets are incomplete; runtime will fail open loudly",
            required=False,
        ))
    return results


def validate_identity_feature_dependencies(policy: dict, profile: str) -> list[dict]:
    results: list[dict] = []
    feature_cfg = policy.get("feature_dependencies", {})
    config_path = ROOT / "configs/runtime/identity.yaml"
    if not config_path.exists():
        results.append(check("identity config", False, str(config_path), required=True))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("identity config parseable", False, str(exc), required=True))
        return results

    identity = cfg.get("identity", cfg)
    fail_open = bool(_get_nested(identity, "fail_open", True))

    face_enabled = bool(_get_nested(identity, "face.enabled", False))
    if face_enabled:
        print("\n[Feature Dependencies â€” identity.face]")
        required = profile == "production" or not fail_open
        for module_cfg in feature_cfg.get("identity_face", {}).get("modules", []):
            ok = _try_import(module_cfg["module"])
            detail = "available" if ok else f"missing; install: {module_cfg.get('install_hint', '')}"
            results.append(check(module_cfg["module"], ok, detail, required=required))
        try:
            from ml.runtime.model_router import ModelRouter

            face_model = ModelRouter().get_model("face")
            results.append(check("identity face model bundle", True, face_model.get("resolved_path", ""), required=required))
        except Exception as exc:
            results.append(check("identity face model bundle", False, str(exc), required=required))

    reid_enabled = bool(_get_nested(identity, "reid.enabled", False))
    if reid_enabled:
        print("\n[Feature Dependencies â€” identity.reid]")
        required = profile == "production" or not fail_open
        for module_cfg in feature_cfg.get("identity_reid", {}).get("modules", []):
            ok = _try_import(module_cfg["module"])
            detail = "available" if ok else f"missing; install: {module_cfg.get('install_hint', '')}"
            results.append(check(module_cfg["module"], ok, detail, required=required))

    liveness_enabled = bool(_get_nested(identity, "liveness.enabled", False))
    if liveness_enabled:
        print("\n[Feature Dependencies â€” identity.liveness]")
        provider = str(_get_nested(identity, "liveness.provider", "pending"))
        results.append(check(
            feature_cfg.get("identity_liveness", {}).get("label", "Identity liveness provider"),
            False,
            f"provider '{provider}' is pending integration",
            required=profile == "production",
        ))
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
        "configs/runtime/identity.yaml",
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
