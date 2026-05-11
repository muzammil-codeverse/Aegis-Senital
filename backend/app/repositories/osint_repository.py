from __future__ import annotations

import json
import os
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from app.models.osint_models import CaseDocumentSummary, CaseEnrichmentAuditLog, CaseExternalSource

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover
    psycopg2 = None
    Json = None
    RealDictCursor = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OSINT_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "osint_enrichment.yaml"
PRODUCTION_ENVS = {"prod", "production"}
_OSINT_REPOSITORY: "OsintRepository | None" = None
_OSINT_REPOSITORY_LOCK = threading.Lock()


def _environment_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "development").strip().lower()


def _is_production() -> bool:
    return _environment_name() in PRODUCTION_ENVS


def load_osint_config() -> dict[str, Any]:
    if not OSINT_CONFIG_PATH.exists():
        return {"osint_enrichment": {"enabled": False}}
    with OSINT_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid osint enrichment config: {OSINT_CONFIG_PATH}")
    return payload


def _parse_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    from datetime import datetime

    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


class OsintRepository(ABC):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict(self._raw_config.get("osint_enrichment") or {})
        self._enabled = bool(self._config.get("enabled", True))
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    @abstractmethod
    def storage_backend(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_source(self, source: CaseExternalSource) -> CaseExternalSource:
        raise NotImplementedError

    @abstractmethod
    def get_source(self, source_id: str) -> CaseExternalSource | None:
        raise NotImplementedError

    @abstractmethod
    def list_sources(self, case_id: str) -> list[CaseExternalSource]:
        raise NotImplementedError

    @abstractmethod
    def update_source(self, source_id: str, updates: dict[str, Any]) -> CaseExternalSource:
        raise NotImplementedError

    @abstractmethod
    def delete_source(self, source_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def save_summary(self, summary: CaseDocumentSummary) -> CaseDocumentSummary:
        raise NotImplementedError

    @abstractmethod
    def list_summaries(self, case_id: str) -> list[CaseDocumentSummary]:
        raise NotImplementedError

    @abstractmethod
    def add_audit_log(self, log: CaseEnrichmentAuditLog) -> CaseEnrichmentAuditLog:
        raise NotImplementedError

    @abstractmethod
    def list_audit_logs(self, case_id: str) -> list[CaseEnrichmentAuditLog]:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            status = "disabled"
        elif self.is_available():
            status = "healthy"
        else:
            status = "failed" if _is_production() else "degraded"
        return {
            "enabled": self.enabled,
            "mode": str(self._config.get("mode") or "analyst_provided_only"),
            "storage": self.storage_backend,
            "status": status,
            "last_error": self._last_error,
        }

    def _set_error(self, message: str | None) -> None:
        self._last_error = message

    def _require_available(self) -> None:
        if not self.is_available():
            raise RuntimeError(self._last_error or "OSINT repository is unavailable")


class JsonlOsintRepository(OsintRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        storage_cfg = dict(self._config.get("storage") or {})
        self._storage_dir = (PROJECT_ROOT / str(storage_cfg.get("jsonl_dir") or "storage/osint")).resolve()
        self._paths = {
            "sources": self._storage_dir / "enrichment_sources.jsonl",
            "summaries": self._storage_dir / "enrichment_summaries.jsonl",
            "audit": self._storage_dir / "enrichment_audit.jsonl",
        }
        self._lock = threading.RLock()
        self._sources: dict[str, CaseExternalSource] = {}
        self._summaries: dict[str, list[CaseDocumentSummary]] = {}
        self._audit: dict[str, list[CaseEnrichmentAuditLog]] = {}
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            for path in self._paths.values():
                path.touch(exist_ok=True)
            self._load_all()
            self._set_error(None)
        except Exception as exc:
            self._set_error(str(exc))

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._storage_dir), os.W_OK)

    def create_source(self, source: CaseExternalSource) -> CaseExternalSource:
        self._require_available()
        with self._lock:
            self._sources[source.source_id] = source
            self._append(self._paths["sources"], source.model_dump(mode="json"))
        return source

    def get_source(self, source_id: str) -> CaseExternalSource | None:
        with self._lock:
            return self._sources.get(source_id)

    def list_sources(self, case_id: str) -> list[CaseExternalSource]:
        with self._lock:
            items = [item for item in self._sources.values() if item.case_id == case_id]
        items.sort(key=lambda item: _parse_timestamp(item.created_at))
        return items

    def update_source(self, source_id: str, updates: dict[str, Any]) -> CaseExternalSource:
        self._require_available()
        with self._lock:
            existing = self._sources.get(source_id)
            if existing is None:
                raise KeyError(source_id)
            payload = existing.model_dump(mode="json")
            payload.update({key: value for key, value in updates.items() if value is not None})
            source = CaseExternalSource.model_validate(payload)
            self._sources[source_id] = source
            self._append(self._paths["sources"], source.model_dump(mode="json"))
        return source

    def delete_source(self, source_id: str) -> bool:
        self._require_available()
        with self._lock:
            if source_id not in self._sources:
                return False
            self._sources.pop(source_id, None)
            self._append(self._paths["sources"], {"source_id": source_id, "_deleted": True})
        return True

    def save_summary(self, summary: CaseDocumentSummary) -> CaseDocumentSummary:
        self._require_available()
        with self._lock:
            self._summaries.setdefault(summary.case_id, []).append(summary)
            self._append(self._paths["summaries"], summary.model_dump(mode="json"))
        return summary

    def list_summaries(self, case_id: str) -> list[CaseDocumentSummary]:
        with self._lock:
            items = list(self._summaries.get(case_id, []))
        items.sort(key=lambda item: _parse_timestamp(item.created_at))
        return items

    def add_audit_log(self, log: CaseEnrichmentAuditLog) -> CaseEnrichmentAuditLog:
        self._require_available()
        with self._lock:
            self._audit.setdefault(log.case_id, []).append(log)
            self._append(self._paths["audit"], log.model_dump(mode="json"))
        return log

    def list_audit_logs(self, case_id: str) -> list[CaseEnrichmentAuditLog]:
        with self._lock:
            items = list(self._audit.get(case_id, []))
        items.sort(key=lambda item: _parse_timestamp(item.timestamp))
        return items

    def _append(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _load_all(self) -> None:
        with self._paths["sources"].open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if payload.get("_deleted"):
                    self._sources.pop(str(payload.get("source_id")), None)
                    continue
                source = CaseExternalSource.model_validate(payload)
                self._sources[source.source_id] = source
        with self._paths["summaries"].open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                summary = CaseDocumentSummary.model_validate(json.loads(line))
                self._summaries.setdefault(summary.case_id, []).append(summary)
        with self._paths["audit"].open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                log = CaseEnrichmentAuditLog.model_validate(json.loads(line))
                self._audit.setdefault(log.case_id, []).append(log)


class PostgresOsintRepository(OsintRepository):
    _DDL = """
    CREATE TABLE IF NOT EXISTS osint_sources (
        source_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NULL,
        storage_uri TEXT NULL,
        original_filename TEXT NULL,
        safe_filename TEXT NULL,
        content_type TEXT NULL,
        size_bytes BIGINT NULL,
        hash_sha256 TEXT NULL,
        hash_verified BOOLEAN NULL,
        integrity_status TEXT NOT NULL DEFAULT 'not_applicable',
        last_verified_at TIMESTAMPTZ NULL,
        description TEXT NOT NULL,
        source_reliability TEXT NOT NULL,
        analyst_provided BOOLEAN NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        summary TEXT NULL,
        requires_review BOOLEAN NOT NULL
    );
    CREATE TABLE IF NOT EXISTS osint_summaries (
        summary_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        summary TEXT NOT NULL,
        key_points JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_references JSONB NOT NULL DEFAULT '[]'::jsonb,
        operator_review_caveat TEXT NOT NULL,
        limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS osint_audit (
        enrichment_audit_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        source_id TEXT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        detail TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._dsn = os.getenv("POSTGRES_DSN") or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("DB_URL")
        self._available = False
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def create_source(self, source: CaseExternalSource) -> CaseExternalSource:
        self._require_available()
        query = """
            INSERT INTO osint_sources (
                source_id, case_id, source_type, title, url, storage_uri, original_filename, safe_filename,
                content_type, size_bytes, hash_sha256, hash_verified, integrity_status, last_verified_at, description,
                source_reliability, analyst_provided, created_by, created_at, metadata, summary, requires_review
            ) VALUES (
                %(source_id)s, %(case_id)s, %(source_type)s, %(title)s, %(url)s, %(storage_uri)s, %(original_filename)s, %(safe_filename)s,
                %(content_type)s, %(size_bytes)s, %(hash_sha256)s, %(hash_verified)s, %(integrity_status)s, %(last_verified_at)s, %(description)s,
                %(source_reliability)s, %(analyst_provided)s, %(created_by)s, %(created_at)s, %(metadata)s, %(summary)s, %(requires_review)s
            )
        """
        self._execute(query, {**source.model_dump(mode="json"), "metadata": Json(source.metadata)})
        return source

    def get_source(self, source_id: str) -> CaseExternalSource | None:
        row = self._fetchone("SELECT * FROM osint_sources WHERE source_id = %(source_id)s", {"source_id": source_id})
        return CaseExternalSource.model_validate(dict(row)) if row else None

    def list_sources(self, case_id: str) -> list[CaseExternalSource]:
        rows = self._fetchall("SELECT * FROM osint_sources WHERE case_id = %(case_id)s ORDER BY created_at ASC", {"case_id": case_id})
        return [CaseExternalSource.model_validate(dict(row)) for row in rows]

    def update_source(self, source_id: str, updates: dict[str, Any]) -> CaseExternalSource:
        existing = self.get_source(source_id)
        if existing is None:
            raise KeyError(source_id)
        payload = existing.model_dump(mode="json")
        payload.update({key: value for key, value in updates.items() if value is not None})
        source = CaseExternalSource.model_validate(payload)
        query = """
            UPDATE osint_sources
            SET case_id = %(case_id)s,
                source_type = %(source_type)s,
                title = %(title)s,
                url = %(url)s,
                storage_uri = %(storage_uri)s,
                original_filename = %(original_filename)s,
                safe_filename = %(safe_filename)s,
                content_type = %(content_type)s,
                size_bytes = %(size_bytes)s,
                hash_sha256 = %(hash_sha256)s,
                hash_verified = %(hash_verified)s,
                integrity_status = %(integrity_status)s,
                last_verified_at = %(last_verified_at)s,
                description = %(description)s,
                source_reliability = %(source_reliability)s,
                analyst_provided = %(analyst_provided)s,
                created_by = %(created_by)s,
                created_at = %(created_at)s,
                metadata = %(metadata)s,
                summary = %(summary)s,
                requires_review = %(requires_review)s
            WHERE source_id = %(source_id)s
        """
        self._execute(query, {**source.model_dump(mode="json"), "metadata": Json(source.metadata)})
        return source

    def delete_source(self, source_id: str) -> bool:
        self._require_available()
        self._execute("DELETE FROM osint_sources WHERE source_id = %(source_id)s", {"source_id": source_id})
        return True

    def save_summary(self, summary: CaseDocumentSummary) -> CaseDocumentSummary:
        self._require_available()
        query = """
            INSERT INTO osint_summaries (
                summary_id, case_id, source_ids, summary, key_points, source_references,
                operator_review_caveat, limitations, provider, model, created_by, created_at, metadata
            ) VALUES (
                %(summary_id)s, %(case_id)s, %(source_ids)s, %(summary)s, %(key_points)s, %(source_references)s,
                %(operator_review_caveat)s, %(limitations)s, %(provider)s, %(model)s, %(created_by)s, %(created_at)s, %(metadata)s
            )
        """
        self._execute(
            query,
            {
                **summary.model_dump(mode="json"),
                "source_ids": Json(summary.source_ids),
                "key_points": Json(summary.key_points),
                "source_references": Json(summary.source_references),
                "limitations": Json(summary.limitations),
                "metadata": Json(summary.metadata),
            },
        )
        return summary

    def list_summaries(self, case_id: str) -> list[CaseDocumentSummary]:
        rows = self._fetchall("SELECT * FROM osint_summaries WHERE case_id = %(case_id)s ORDER BY created_at ASC", {"case_id": case_id})
        return [CaseDocumentSummary.model_validate(dict(row)) for row in rows]

    def add_audit_log(self, log: CaseEnrichmentAuditLog) -> CaseEnrichmentAuditLog:
        self._require_available()
        query = """
            INSERT INTO osint_audit (
                enrichment_audit_id, case_id, source_id, action, actor, timestamp, detail, metadata
            ) VALUES (
                %(enrichment_audit_id)s, %(case_id)s, %(source_id)s, %(action)s, %(actor)s, %(timestamp)s, %(detail)s, %(metadata)s
            )
        """
        self._execute(query, {**log.model_dump(mode="json"), "metadata": Json(log.metadata)})
        return log

    def list_audit_logs(self, case_id: str) -> list[CaseEnrichmentAuditLog]:
        rows = self._fetchall("SELECT * FROM osint_audit WHERE case_id = %(case_id)s ORDER BY timestamp ASC", {"case_id": case_id})
        return [CaseEnrichmentAuditLog.model_validate(dict(row)) for row in rows]

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for statement in [part.strip() for part in self._DDL.split(";") if part.strip()]:
                        cursor.execute(statement)
                    for statement in (
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS original_filename TEXT NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS safe_filename TEXT NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS content_type TEXT NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS size_bytes BIGINT NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS hash_sha256 TEXT NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS hash_verified BOOLEAN NULL",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS integrity_status TEXT NOT NULL DEFAULT 'not_applicable'",
                        "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ NULL",
                    ):
                        cursor.execute(statement)
                conn.commit()
            self._available = True
            self._set_error(None)
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))

    def _connect(self):
        return psycopg2.connect(self._dsn, connect_timeout=3, cursor_factory=RealDictCursor)

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                conn.commit()
            self._available = True
            self._set_error(None)
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))
            raise
        finally:
            _record_osint_latency((time.monotonic() - started) * 1000.0)

    def _fetchone(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        started = time.monotonic()
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
            self._available = True
            self._set_error(None)
            return row
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))
            raise
        finally:
            _record_osint_latency((time.monotonic() - started) * 1000.0)

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        started = time.monotonic()
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
            self._available = True
            self._set_error(None)
            return rows
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))
            raise
        finally:
            _record_osint_latency((time.monotonic() - started) * 1000.0)


def _record_osint_latency(value_ms: float) -> None:
    rounded = round(max(0.0, value_ms), 2)
    try:
        from inference.monitoring.metrics import get_metrics

        get_metrics().record_segmentation_value("osint_storage_latency_ms", rounded)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as system_metrics

        system_metrics.set_value("osint_storage_latency_ms", rounded)
    except Exception:
        pass


def build_osint_repository(config: dict[str, Any] | None = None) -> OsintRepository:
    payload = config or load_osint_config()
    osint_cfg = dict(payload.get("osint_enrichment") or {})
    if _is_production() and bool(osint_cfg.get("enabled", True)):
        return PostgresOsintRepository(config=payload)
    return JsonlOsintRepository(config=payload)


def get_osint_repository() -> OsintRepository:
    global _OSINT_REPOSITORY
    if _OSINT_REPOSITORY is None:
        with _OSINT_REPOSITORY_LOCK:
            if _OSINT_REPOSITORY is None:
                _OSINT_REPOSITORY = build_osint_repository()
    return _OSINT_REPOSITORY


def set_osint_repository(repository: OsintRepository) -> None:
    global _OSINT_REPOSITORY
    with _OSINT_REPOSITORY_LOCK:
        _OSINT_REPOSITORY = repository


def reset_osint_repository() -> None:
    global _OSINT_REPOSITORY
    with _OSINT_REPOSITORY_LOCK:
        _OSINT_REPOSITORY = None
