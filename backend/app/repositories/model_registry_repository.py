from __future__ import annotations

import json
import os
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.persistence import (
    RepositoryHealth,
    is_production_environment,
    postgres_dsn,
)
from app.db.schema_bootstrap import bootstrap_schema

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_REGISTRY_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "model_registry.yaml"
_DEFAULT_RESERVED_REGISTRY_KEYS = frozenset({"active_version", "active_rollout"})


DEFAULT_MODEL_REGISTRY_CONFIG: dict[str, Any] = {
    "model_registry": {
        "backend": "file",
        "file_path": "models/registry.json",
        "allow_file_to_db_migration": True,
        "prohibit_dual_writes": True,
        "enable_postgres_writes": False,
        "enable_file_writes": False,
    }
}
_MODEL_REGISTRY_REPOSITORY: "ModelRegistryRepository | None" = None
_MODEL_REGISTRY_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def load_model_registry_config() -> dict[str, Any]:
    if not MODEL_REGISTRY_CONFIG_PATH.exists():
        return DEFAULT_MODEL_REGISTRY_CONFIG
    payload = yaml.safe_load(MODEL_REGISTRY_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid model registry config: {MODEL_REGISTRY_CONFIG_PATH}")
    return _deep_merge(DEFAULT_MODEL_REGISTRY_CONFIG, payload)


def reset_model_registry_config_cache() -> None:
    load_model_registry_config.cache_clear()


def get_model_registry_settings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = config or load_model_registry_config()
    settings = dict(payload.get("model_registry") or {})
    if not settings:
        return dict(DEFAULT_MODEL_REGISTRY_CONFIG["model_registry"])
    return settings


@dataclass(slots=True)
class ModelRegistryEntry:
    entry_id: str
    model_id: str
    model_key: str
    model_name: str
    version: str
    path: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "model_id": self.model_id,
            "model_key": self.model_key,
            "model_name": self.model_name,
            "version": self.version,
            "path": self.path,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _entry_id(model_key: str, version: str) -> str:
    return f"mreg_{model_key}_{version}".replace("/", "_")


def _normalize_direct_entry(model_key: str, payload: dict[str, Any]) -> ModelRegistryEntry:
    version = str(payload.get("version") or "current")
    model_id = model_key if version == "current" else f"{model_key}/{version}"
    created_at = str(payload.get("created_at") or _now_iso())
    return ModelRegistryEntry(
        entry_id=_entry_id(model_key, version),
        model_id=model_id,
        model_key=model_key,
        model_name=str(payload.get("model_name") or model_key),
        version=version,
        path=str(payload.get("path") or ""),
        metadata={
            key: value
            for key, value in payload.items()
            if key not in {"model_name", "version", "path"}
        },
        created_at=created_at,
        updated_at=str(payload.get("updated_at") or created_at),
    )


def flatten_registry_snapshot(snapshot: dict[str, Any]) -> list[ModelRegistryEntry]:
    items: list[ModelRegistryEntry] = []
    for model_key, payload in (snapshot or {}).items():
        if not isinstance(payload, dict):
            continue
        if "path" in payload:
            items.append(_normalize_direct_entry(str(model_key), payload))
            continue
        versioned = [
            item
            for item in payload.items()
            if isinstance(item[1], dict)
            and "path" in item[1]
            and str(item[0]) not in _DEFAULT_RESERVED_REGISTRY_KEYS
        ]
        if not versioned:
            continue
        for version, meta in versioned:
            items.append(
                ModelRegistryEntry(
                    entry_id=_entry_id(str(model_key), str(version)),
                    model_id=f"{model_key}/{version}",
                    model_key=str(model_key),
                    model_name=str(meta.get("model_name") or model_key),
                    version=str(meta.get("version") or version),
                    path=str(meta.get("path") or ""),
                    metadata={
                        key: value
                        for key, value in meta.items()
                        if key not in {"model_name", "version", "path"}
                    },
                    created_at=str(meta.get("created_at") or _now_iso()),
                    updated_at=str(meta.get("updated_at") or meta.get("created_at") or _now_iso()),
                )
            )
    items.sort(key=lambda item: (item.model_key, item.version))
    return items


def grouped_registry_entries(entries: list[ModelRegistryEntry]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(entry.model_key, {})[entry.version] = {
            "model_name": entry.model_name,
            "version": entry.version,
            "path": entry.path,
            **dict(entry.metadata),
        }
    return grouped


def _latest_entry(entries: list[ModelRegistryEntry]) -> ModelRegistryEntry | None:
    if not entries:
        return None
    return sorted(entries, key=lambda item: (str(item.created_at), item.version, item.model_id))[-1]


class ModelRegistryRepository(ABC):
    def __init__(self, *, allow_writes: bool = False) -> None:
        self._allow_writes = allow_writes
        self._last_error: str | None = None

    @property
    @abstractmethod
    def storage_backend(self) -> str:
        raise NotImplementedError

    @property
    def allow_writes(self) -> bool:
        return self._allow_writes

    def read_snapshot(self) -> dict[str, Any]:
        """Raw registry document (file JSON or reconstructed). Used for governance / active_version."""
        return {}

    def write_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Replace registry document atomically (file backend only in standard deployments)."""
        self._raise_if_writes_disabled()
        raise RuntimeError("write_snapshot is not implemented for this registry backend")

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_entries(self) -> list[ModelRegistryEntry]:
        raise NotImplementedError

    def grouped_entries(self) -> dict[str, dict[str, dict[str, Any]]]:
        return grouped_registry_entries(self.list_entries())

    def get_entry(self, model_id: str) -> ModelRegistryEntry | None:
        for entry in self.list_entries():
            if entry.model_id == model_id:
                return entry
        return None

    def resolve_model(self, model_key: str) -> ModelRegistryEntry | None:
        entries = [item for item in self.list_entries() if item.model_key == model_key]
        return _latest_entry(entries)

    @abstractmethod
    def upsert_entries(self, entries: list[ModelRegistryEntry]) -> int:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        status = "healthy" if self.is_available() else ("failed" if is_production_environment() else "degraded")
        return RepositoryHealth(
            store="model_registry",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
            extra={"allow_writes": self.allow_writes},
        )

    def _raise_if_writes_disabled(self) -> None:
        if not self.allow_writes:
            raise RuntimeError("Model registry writes are disabled to prevent split-brain state")

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class FileModelRegistryRepository(ModelRegistryRepository):
    def __init__(self, file_path: str, *, allow_writes: bool = False) -> None:
        super().__init__(allow_writes=allow_writes)
        self._file_path = (PROJECT_ROOT / file_path).resolve()

    @property
    def storage_backend(self) -> str:
        return "file"

    @property
    def file_path(self) -> Path:
        return self._file_path

    def is_available(self) -> bool:
        return self._file_path.exists()

    def list_entries(self) -> list[ModelRegistryEntry]:
        if not self._file_path.exists():
            return []
        payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        return flatten_registry_snapshot(payload if isinstance(payload, dict) else {})

    def read_snapshot(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {}
        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Atomically replace registry JSON (governance rollback / promotion metadata only)."""
        self._raise_if_writes_disabled()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp.replace(self._file_path)
        self._set_error(None)

    def upsert_entries(self, entries: list[ModelRegistryEntry]) -> int:
        self._raise_if_writes_disabled()
        raise RuntimeError("File registry row upserts are not supported; use write_snapshot via governance service")


class PostgresModelRegistryRepository(ModelRegistryRepository):
    def __init__(self, *, allow_writes: bool = False) -> None:
        super().__init__(allow_writes=allow_writes)
        self._dsn = postgres_dsn()
        self._available = False
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def read_snapshot(self) -> dict[str, Any]:
        entries = self.list_entries()
        snapshot: dict[str, Any] = {}
        for entry in entries:
            grouped = snapshot.setdefault(entry.model_key, {})
            if isinstance(grouped, dict):
                grouped[str(entry.version)] = {
                    "model_name": entry.model_name,
                    "version": entry.version,
                    "path": entry.path,
                    **dict(entry.metadata),
                }
        return snapshot

    def list_entries(self) -> list[ModelRegistryEntry]:
        rows = self._fetchall(
            """
            SELECT entry_id, model_key, model_name, version, path, metadata, created_at, updated_at
            FROM model_registry_entries
            ORDER BY model_key ASC, created_at ASC, version ASC
            """,
            {},
        )
        items: list[ModelRegistryEntry] = []
        for row in rows:
            payload = dict(row.get("metadata") or {})
            model_key = str(row.get("model_key") or "")
            version = str(row.get("version") or "current")
            model_id = model_key if version == "current" else f"{model_key}/{version}"
            items.append(
                ModelRegistryEntry(
                    entry_id=str(row.get("entry_id") or _entry_id(model_key, version)),
                    model_id=model_id,
                    model_key=model_key,
                    model_name=str(row.get("model_name") or model_key),
                    version=version,
                    path=str(row.get("path") or ""),
                    metadata=payload,
                    created_at=str(row.get("created_at") or _now_iso()),
                    updated_at=str(row.get("updated_at") or row.get("created_at") or _now_iso()),
                )
            )
        return items

    def upsert_entries(self, entries: list[ModelRegistryEntry]) -> int:
        self._raise_if_writes_disabled()
        count = 0
        query = """
            INSERT INTO model_registry_entries (
                entry_id, model_key, model_name, version, path, metadata, created_at, updated_at
            )
            VALUES (
                %(entry_id)s, %(model_key)s, %(model_name)s, %(version)s, %(path)s, %(metadata)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (entry_id) DO UPDATE SET
                model_key = EXCLUDED.model_key,
                model_name = EXCLUDED.model_name,
                version = EXCLUDED.version,
                path = EXCLUDED.path,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
        """
        for entry in entries:
            params = entry.to_dict()
            params["metadata"] = Json(params.get("metadata") or {})
            self._execute(query, params)
            count += 1
        return count

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("model_registry_entries",))
            self._available = True
            self._set_error(None)
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))

    def _connect(self):
        return psycopg2.connect(self._dsn, connect_timeout=3, cursor_factory=RealDictCursor)

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()
        self._available = True
        self._set_error(None)

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        self._available = True
        self._set_error(None)
        return rows


def build_model_registry_repository(config: dict[str, Any] | None = None) -> ModelRegistryRepository:
    settings = get_model_registry_settings(config)
    backend = str(settings.get("backend") or "file").strip().lower()
    allow_writes = bool(settings.get("enable_postgres_writes", False))
    if backend == "postgres":
        return PostgresModelRegistryRepository(allow_writes=allow_writes)
    file_writes = bool(settings.get("enable_file_writes", False))
    return FileModelRegistryRepository(
        str(settings.get("file_path") or "models/registry.json"),
        allow_writes=file_writes,
    )


def get_model_registry_repository(config: dict[str, Any] | None = None) -> ModelRegistryRepository:
    global _MODEL_REGISTRY_REPOSITORY
    with _MODEL_REGISTRY_LOCK:
        if _MODEL_REGISTRY_REPOSITORY is None:
            _MODEL_REGISTRY_REPOSITORY = build_model_registry_repository(config)
        return _MODEL_REGISTRY_REPOSITORY


def reset_model_registry_repository() -> None:
    global _MODEL_REGISTRY_REPOSITORY
    with _MODEL_REGISTRY_LOCK:
        _MODEL_REGISTRY_REPOSITORY = None
