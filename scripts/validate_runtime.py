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
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
POLICY_PATH = ROOT / "configs" / "runtime" / "dependency_policy.yaml"
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


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


def _resolve_ffmpeg_binary() -> str | None:
    explicit = (os.environ.get("AEGIS_FFMPEG_PATH") or os.environ.get("FFMPEG_BINARY") or "").strip()
    if explicit:
        return explicit

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        winget_link = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        try:
            target = os.readlink(str(winget_link))
            return target.replace("\\\\?\\", "")
        except OSError:
            pass
    return None


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


def validate_llm_configuration(profile: str) -> list[dict]:
    results: list[dict] = []
    print("\n[LLM Configuration]")
    config_path = ROOT / "configs" / "runtime" / "llm.yaml"
    if not config_path.exists():
        results.append(check("llm config", False, str(config_path), required=True))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("llm config parseable", False, str(exc), required=True))
        return results

    llm_cfg = cfg.get("llm", cfg)
    enabled = bool(llm_cfg.get("enabled", False))
    provider = str(llm_cfg.get("provider") or llm_cfg.get("default_provider") or "local_stub").lower()
    results.append(check("llm enabled", True, "enabled" if enabled else "disabled", required=False))
    results.append(check("llm provider", True, provider, required=False))
    if not enabled:
        return results

    providers = dict(llm_cfg.get("providers") or {})
    openai_cfg = dict(providers.get("openai") or {})
    local_stub_cfg = dict(providers.get("local_stub") or {})
    api_key_env = str(openai_cfg.get("api_key_env") or "OPENAI_API_KEY")
    api_key_present = bool(os.environ.get(api_key_env, "").strip())
    fallback_allowed = bool((llm_cfg.get("development") or {}).get("allow_local_stub_if_openai_key_missing", True))
    production_fail = bool((llm_cfg.get("production") or {}).get("fail_if_openai_key_missing", True))

    if provider == "openai":
        results.append(check("openai package", _try_import("openai"), "available" if _try_import("openai") else "missing; install: pip install openai", required=True))
        key_required = profile == "production" and production_fail
        if api_key_present:
            results.append(check(api_key_env, True, "configured", required=key_required))
        else:
            detail = "missing"
            if profile == "development" and fallback_allowed and bool(local_stub_cfg.get("enabled", True)):
                detail = "missing; local_stub fallback is allowed in development"
            results.append(check(api_key_env, False, detail, required=key_required))
    else:
        results.append(check("local_stub provider", bool(local_stub_cfg.get("enabled", True)), "enabled" if local_stub_cfg.get("enabled", True) else "disabled", required=False))

    return results


def validate_osint_configuration(profile: str) -> list[dict]:
    results: list[dict] = []
    print("\n[OSINT Enrichment]")
    config_path = ROOT / "configs" / "runtime" / "osint_enrichment.yaml"
    if not config_path.exists():
        results.append(check("osint enrichment config", False, str(config_path), required=True))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("osint enrichment config parseable", False, str(exc), required=True))
        return results

    osint_cfg = cfg.get("osint_enrichment", cfg)
    enabled = bool(osint_cfg.get("enabled", False))
    mode = str(osint_cfg.get("mode") or "analyst_provided_only")
    results.append(check("osint enrichment enabled", True, "enabled" if enabled else "disabled", required=False))
    results.append(check("osint enrichment mode", mode == "analyst_provided_only", mode, required=True))
    if not enabled:
        return results

    uploads_cfg = dict(osint_cfg.get("uploads") or {})
    upload_dir = ROOT / str(uploads_cfg.get("storage_dir") or "storage/osint_uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    results.append(check("storage/osint_uploads", os.access(str(upload_dir), os.W_OK), str(upload_dir), required=profile == "development"))

    jsonl_dir = ROOT / "storage" / "osint"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    results.append(check("storage/osint", os.access(str(jsonl_dir), os.W_OK), str(jsonl_dir), required=profile == "development"))

    links_cfg = dict(osint_cfg.get("links") or {})
    results.append(check("osint fetch_full_page disabled", not bool(links_cfg.get("fetch_full_page", False)), "disabled" if not bool(links_cfg.get("fetch_full_page", False)) else "enabled", required=True))
    results.append(check("osint fetch_preview disabled", not bool(links_cfg.get("fetch_preview", False)), "disabled" if not bool(links_cfg.get("fetch_preview", False)) else "enabled", required=True))

    prod_fail = bool((osint_cfg.get("production") or {}).get("fail_if_storage_unavailable", True))
    if profile == "production" and prod_fail:
        dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("AEGIS_POSTGRES_DSN") or os.environ.get("DB_URL")
        results.append(check("osint enrichment postgres dsn", bool(dsn), "configured" if dsn else "missing POSTGRES_DSN", required=True))

    return results


def validate_evidence_configuration(profile: str) -> list[dict]:
    results: list[dict] = []
    print("\n[Evidence]")
    config_path = ROOT / "configs" / "runtime" / "evidence.yaml"
    if not config_path.exists():
        results.append(check("evidence config", False, str(config_path), required=True))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("evidence config parseable", False, str(exc), required=True))
        return results

    evidence_cfg = cfg.get("evidence", cfg)
    enabled = bool(evidence_cfg.get("enabled", False))
    results.append(check("evidence enabled", True, "enabled" if enabled else "disabled", required=False))
    if not enabled:
        return results

    storage_cfg = dict(evidence_cfg.get("storage") or {})
    local_dir = ROOT / str(storage_cfg.get("local_dir") or "storage/evidence")
    local_dir.mkdir(parents=True, exist_ok=True)
    results.append(check("storage/evidence", os.access(str(local_dir), os.W_OK), str(local_dir), required=profile == "production"))

    hashing_cfg = dict(evidence_cfg.get("hashing") or {})
    algorithm = str(hashing_cfg.get("algorithm") or "sha256").lower()
    results.append(check("evidence hashing algorithm", algorithm == "sha256", algorithm, required=True))
    results.append(check(
        "evidence file hashing required",
        bool(hashing_cfg.get("required_for_file_backed_evidence", True)),
        "required" if bool(hashing_cfg.get("required_for_file_backed_evidence", True)) else "disabled",
        required=True,
    ))

    identity_cfg_path = ROOT / "configs" / "runtime" / "identity.yaml"
    try:
        identity_cfg = yaml.safe_load(identity_cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        identity_cfg = {}
    raw_asset_cfg = dict((identity_cfg.get("identity", identity_cfg) or {}).get("raw_asset_access") or {})
    results.append(check(
        "identity raw asset http access",
        not bool(raw_asset_cfg.get("enabled", False)),
        "disabled" if not bool(raw_asset_cfg.get("enabled", False)) else "enabled",
        required=True,
    ))
    return results


def validate_streaming_configuration(profile: str) -> list[dict]:
    results: list[dict] = []
    print("\n[Streaming]")
    config_path = ROOT / "configs" / "runtime" / "streaming.yaml"
    if not config_path.exists():
        results.append(check("streaming config", False, str(config_path), required=True))
        return results
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        results.append(check("streaming config parseable", False, str(exc), required=True))
        return results

    streaming_cfg = cfg.get("streaming", cfg)
    enabled = bool(streaming_cfg.get("enabled", True))
    webrtc_enabled = bool(streaming_cfg.get("webrtc", {}).get("enabled", False))
    hls_enabled = bool(streaming_cfg.get("hls", {}).get("enabled", False))
    replay_enabled = bool(streaming_cfg.get("replay", {}).get("enabled", False))
    results.append(check("streaming enabled", True, "enabled" if enabled else "disabled", required=False))
    results.append(check("streaming webrtc", True, "enabled" if webrtc_enabled else "disabled", required=False))
    results.append(check("streaming hls", True, "enabled" if hls_enabled else "disabled", required=False))
    results.append(check("streaming replay", True, "enabled" if replay_enabled else "disabled", required=False))
    if not enabled:
        return results

    hls_dir = ROOT / str(streaming_cfg.get("hls", {}).get("output_dir") or "storage/hls")
    replay_dir = ROOT / str(streaming_cfg.get("replay", {}).get("output_dir") or "storage/replay")
    hls_dir.mkdir(parents=True, exist_ok=True)
    replay_dir.mkdir(parents=True, exist_ok=True)
    results.append(check("streaming hls output", os.access(str(hls_dir), os.W_OK), str(hls_dir), required=profile == "production"))
    results.append(check("streaming replay output", os.access(str(replay_dir), os.W_OK), str(replay_dir), required=profile == "production"))

    aiortc_available = _try_import("aiortc")
    ffmpeg_available = bool(_resolve_ffmpeg_binary())
    results.append(check("aiortc", aiortc_available, "available" if aiortc_available else "missing", required=profile == "production" and webrtc_enabled))
    results.append(check("ffmpeg", ffmpeg_available, "available" if ffmpeg_available else "missing", required=profile == "production" and hls_enabled))
    return results


def validate_persistence_configuration(profile: str) -> list[dict]:
    results: list[dict] = []
    print("\n[Persistence]")
    config_path = ROOT / "configs" / "runtime" / "persistence.yaml"
    if not config_path.exists():
        results.append(check("persistence config", False, str(config_path), required=True))
        return results
    try:
        from app.core.persistence import backup_settings, load_persistence_config, persistence_enabled, restore_settings
        from app.services.runtime_health_service import RuntimeHealthService

        persistence_cfg = load_persistence_config()
        persistence_report = RuntimeHealthService(config={"runtime": {}, "services": {}})._check_persistence()
    except Exception as exc:
        results.append(check("persistence config parseable", False, str(exc), required=True))
        return results

    results.append(check("persistence enabled", bool(persistence_enabled(persistence_cfg)), "enabled" if persistence_enabled(persistence_cfg) else "disabled", required=True))
    results.append(check("backup enabled", bool(backup_settings(persistence_cfg).get("enabled", True)), "enabled" if bool(backup_settings(persistence_cfg).get("enabled", True)) else "disabled", required=True))
    results.append(check("restore confirmation required", bool(restore_settings(persistence_cfg).get("require_confirmation", True)), "required" if bool(restore_settings(persistence_cfg).get("require_confirmation", True)) else "disabled", required=True))

    for store_name in ("cases", "evidence_metadata", "evidence_files", "identity_registry", "audit_logs", "osint", "retention_actions"):
        store = dict((persistence_report.get("stores") or {}).get(store_name) or {})
        status = str(store.get("status") or "unknown")
        backend = str(store.get("backend") or "unknown")
        required = profile == "production"
        ok = status not in {"failed", "error"} if profile == "development" else status == "healthy"
        detail = f"{backend} / {status}"
        if store.get("last_error"):
            detail = f"{detail}: {store['last_error']}"
        results.append(check(f"{store_name} store", ok, detail, required=required))

    required_tables = dict(persistence_report.get("required_tables") or {})
    if profile == "production":
        tables_ok = bool(required_tables) and all(required_tables.values())
        missing = [name for name, present in required_tables.items() if not present]
        detail = "all required tables present" if tables_ok else f"missing: {', '.join(missing)}"
        results.append(check("postgres required tables", tables_ok, detail, required=True))
    else:
        detail = "not enforced in development" if not required_tables else "validated"
        results.append(check("postgres required tables", True, detail, required=False))

    if profile == "production":
        failures = persistence_report.get("failures") or []
        results.append(check("production persistence readiness", not failures, "; ".join(failures) if failures else "ready", required=True))
    else:
        warnings = persistence_report.get("warnings") or []
        results.append(check("development persistence readiness", True, "; ".join(warnings) if warnings else "ready", required=False))
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
        "configs/runtime/case_management.yaml",
        "configs/runtime/evidence.yaml",
        "configs/runtime/llm.yaml",
        "configs/runtime/osint_enrichment.yaml",
        "configs/runtime/streaming.yaml",
        "configs/runtime/persistence.yaml",
        "configs/runtime/model_registry.yaml",
        "configs/runtime/uploaded_video.yaml",
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
    try:
        from app.repositories.model_registry_repository import (
            FileModelRegistryRepository,
            get_model_registry_repository,
            get_model_registry_settings,
        )

        settings = get_model_registry_settings()
        repository = get_model_registry_repository()
        health = repository.health_check().to_dict()
        _record(check("model registry repository", health.get("status") == "healthy", health.get("last_error") or "", required=True))
        if isinstance(repository, FileModelRegistryRepository):
            registry_path = repository.file_path
            registry_exists = registry_path.exists()
            _record(check("models/registry.json", registry_exists, required=True))
        else:
            _record(check("model registry backend", repository.storage_backend == "postgres", repository.storage_backend, required=False))
        try:
            entries = repository.list_entries()
            _record(check("model registry entries", len(entries) > 0, f"entries={len(entries)}", required=True))
            grouped = repository.grouped_entries()
            for model_type in ("weapon_detector", "phone_detector"):
                versions = grouped.get(model_type) or {}
                if not versions:
                    _record(check(f"{model_type} registered", False, "missing", required=True))
                    continue
                latest_key = sorted(
                    versions.items(),
                    key=lambda item: (str(item[1].get("created_at", "")), item[0]),
                )[-1][0]
                model_path = ROOT / str((versions.get(latest_key) or {}).get("path") or "MISSING")
                exists = model_path.exists()
                _record(check(
                    f"{model_type} weights",
                    exists,
                    str(model_path) if not exists else "",
                    required=True,
                ))
            if str(settings.get("backend") or "file").lower() == "postgres" and not bool(settings.get("enable_postgres_writes", False)):
                _record(check("model registry write mode", True, "postgres backend read-only until explicitly enabled", required=False))
        except Exception as exc:
            _record(check("model registry parseable", False, str(exc), required=True))
    except Exception as exc:
        _record(check("model registry repository", False, str(exc), required=True))

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

    # Case management
    print("\n[Case Management]")
    case_cfg_path = ROOT / "configs" / "runtime" / "case_management.yaml"
    case_cfg = yaml.safe_load(case_cfg_path.read_text(encoding="utf-8")) if case_cfg_path.exists() else {}
    case_mgmt = (case_cfg or {}).get("case_management", {})
    enabled = bool(case_mgmt.get("enabled", True))
    _record(check("case management enabled", True, "enabled" if enabled else "disabled", required=False))
    if enabled:
        storage_cfg = case_mgmt.get("storage", {})
        jsonl_dir = ROOT / str(storage_cfg.get("jsonl_dir", "storage/cases"))
        jsonl_dir.mkdir(parents=True, exist_ok=True)
        _record(check("storage/cases", os.access(str(jsonl_dir), os.W_OK), str(jsonl_dir), required=profile == "development"))
        prod_backend = str(storage_cfg.get("production_backend", "postgres")).lower()
        require_pg = bool(storage_cfg.get("require_postgres_in_production", True))
        if profile == "production" and prod_backend == "postgres" and require_pg:
            case_dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("AEGIS_POSTGRES_DSN") or os.environ.get("DB_URL")
            _record(check("case management postgres dsn", bool(case_dsn), "configured" if case_dsn else "missing POSTGRES_DSN", required=True))

    # LLM configuration
    llm_results = validate_llm_configuration(profile)
    for r in llm_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(llm_results)

    osint_results = validate_osint_configuration(profile)
    for r in osint_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(osint_results)

    evidence_results = validate_evidence_configuration(profile)
    for r in evidence_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(evidence_results)

    streaming_results = validate_streaming_configuration(profile)
    for r in streaming_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(streaming_results)

    persistence_results = validate_persistence_configuration(profile)
    for r in persistence_results:
        if not r["ok"] and r["required"]:
            required_failures.append(r["name"])
    all_results.extend(persistence_results)

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
