from __future__ import annotations

import os
import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PERSISTENCE_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "persistence.yaml"
PRODUCTION_ENVS = {"prod", "production"}

DEFAULT_PERSISTENCE_CONFIG: dict[str, Any] = {
    "persistence": {
        "enabled": True,
        "development": {
            "allow_jsonl": True,
            "allow_local_filesystem": True,
            "root_dir": "storage",
        },
        "production": {
            "require_postgres": True,
            "require_managed_artifact_storage": True,
            "prohibit_jsonl_fallback_for_required_stores": True,
        },
        "stores": {
            "events": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "cases": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "evidence_metadata": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "evidence_files": {
                "dev_backend": "filesystem",
                "production_backend": "managed_filesystem_or_s3",
                "required_in_production": True,
            },
            "identity_registry": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "audit_logs": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "osint": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
            "analytics": {
                "dev_backend": "derived",
                "production_backend": "postgres",
                "required_in_production": False,
            },
            "retention_actions": {
                "dev_backend": "jsonl",
                "production_backend": "postgres",
                "required_in_production": True,
            },
        },
        "backup": {
            "enabled": True,
            "output_dir": "storage/backups",
            "include_jsonl": True,
            "include_configs": True,
            "include_metadata_only_for_files": True,
        },
        "restore": {
            "enabled": True,
            "require_confirmation": True,
        },
    }
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def environment_name() -> str:
    return (os.getenv("AEGIS_ENV") or os.getenv("APP_ENV") or "development").strip().lower()


def is_production_environment() -> bool:
    return environment_name() in PRODUCTION_ENVS


def postgres_dsn() -> str | None:
    value = os.getenv("POSTGRES_DSN") or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("DB_URL")
    return str(value).strip() or None


@lru_cache(maxsize=1)
def load_persistence_config() -> dict[str, Any]:
    if not PERSISTENCE_CONFIG_PATH.exists():
        return DEFAULT_PERSISTENCE_CONFIG
    with PERSISTENCE_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid persistence config: {PERSISTENCE_CONFIG_PATH}")
    return _deep_merge(DEFAULT_PERSISTENCE_CONFIG, payload)


def reset_persistence_config_cache() -> None:
    load_persistence_config.cache_clear()


def get_persistence_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = config or load_persistence_config()
    settings = dict(payload.get("persistence") or {})
    if not settings:
        return dict(DEFAULT_PERSISTENCE_CONFIG["persistence"])
    return settings


def get_store_policy(store: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_persistence_settings(config)
    stores = dict(settings.get("stores") or {})
    return dict(stores.get(store) or {})


def get_store_backend(
    store: str,
    *,
    config: dict[str, Any] | None = None,
    default_dev: str | None = None,
    default_prod: str | None = None,
) -> str:
    policy = get_store_policy(store, config)
    if is_production_environment():
        return str(policy.get("production_backend") or default_prod or default_dev or "unknown")
    return str(policy.get("dev_backend") or default_dev or default_prod or "unknown")


def store_required_in_production(store: str, config: dict[str, Any] | None = None) -> bool:
    policy = get_store_policy(store, config)
    return bool(policy.get("required_in_production", False))


def prohibit_jsonl_fallback(config: dict[str, Any] | None = None) -> bool:
    settings = get_persistence_settings(config)
    production = dict(settings.get("production") or {})
    return bool(production.get("prohibit_jsonl_fallback_for_required_stores", True))


def require_postgres(config: dict[str, Any] | None = None) -> bool:
    settings = get_persistence_settings(config)
    production = dict(settings.get("production") or {})
    return bool(production.get("require_postgres", True))


def require_managed_artifact_storage(config: dict[str, Any] | None = None) -> bool:
    settings = get_persistence_settings(config)
    production = dict(settings.get("production") or {})
    return bool(production.get("require_managed_artifact_storage", True))


def persistence_enabled(config: dict[str, Any] | None = None) -> bool:
    return bool(get_persistence_settings(config).get("enabled", True))


def backup_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(get_persistence_settings(config).get("backup") or {})


def restore_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(get_persistence_settings(config).get("restore") or {})


def backup_output_dir(config: dict[str, Any] | None = None) -> Path:
    output_dir = str(backup_settings(config).get("output_dir") or "storage/backups")
    return (PROJECT_ROOT / output_dir).resolve()


def development_storage_root(config: dict[str, Any] | None = None) -> Path:
    settings = get_persistence_settings(config)
    development = dict(settings.get("development") or {})
    root_dir = str(development.get("root_dir") or "storage")
    return (PROJECT_ROOT / root_dir).resolve()


@dataclass(slots=True)
class RepositoryHealth:
    store: str
    backend: str
    status: str
    last_error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        extra = payload.pop("extra", {}) or {}
        payload.update(extra)
        return payload


def managed_storage_summary(config: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_persistence_settings(config)
    evidence_policy = get_store_policy("evidence_files", config)
    backend = get_store_backend("evidence_files", config=config, default_dev="filesystem", default_prod="managed_filesystem_or_s3")
    return {
        "required": require_managed_artifact_storage(config),
        "backend": backend,
        "required_in_production": bool(evidence_policy.get("required_in_production", True)),
    }


def latest_backup_manifest(config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    backup_root = backup_output_dir(config)
    if not backup_root.exists():
        return None
    manifests = sorted(
        backup_root.glob("backup_*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["manifest_path"] = str(manifest_path)
            return payload
    return None
