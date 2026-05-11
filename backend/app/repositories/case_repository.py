from __future__ import annotations

import json
import os
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.models.case_models import (
    CaseAuditLog,
    CaseEvidence,
    CaseExport,
    CaseNote,
    CaseRecord,
)

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional in some environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


_CASE_REPOSITORY: "CaseRepository | None" = None
_CASE_REPOSITORY_LOCK = threading.Lock()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "case_management.yaml"
PRODUCTION_ENVS = {"prod", "production"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "development").strip().lower()


def _is_production() -> bool:
    return _environment_name() in PRODUCTION_ENVS


def load_case_management_config() -> dict[str, Any]:
    if not CASE_CONFIG_PATH.exists():
        return {"case_management": {"enabled": False}}
    with CASE_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid case management config: {CASE_CONFIG_PATH}")
    return payload


def _parse_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _match_case_filters(case: CaseRecord, filters: dict[str, Any]) -> bool:
    status = filters.get("status")
    if status:
        allowed = {str(item).lower() for item in (status if isinstance(status, (list, tuple, set)) else [status])}
        if case.status not in allowed:
            return False

    priority = filters.get("priority")
    if priority:
        allowed = {str(item).lower() for item in (priority if isinstance(priority, (list, tuple, set)) else [priority])}
        if case.priority not in allowed:
            return False

    severity = filters.get("severity")
    if severity:
        allowed = {str(item).lower() for item in (severity if isinstance(severity, (list, tuple, set)) else [severity])}
        if case.severity not in allowed:
            return False

    camera_id = filters.get("camera") or filters.get("camera_id")
    if camera_id and str(camera_id) not in case.camera_ids:
        return False

    tag = filters.get("tag")
    if tag and str(tag) not in case.tags:
        return False

    source_event_id = filters.get("source_event_id")
    if source_event_id and str(source_event_id) not in case.source_event_ids:
        return False

    assigned_to = filters.get("assigned_to")
    if assigned_to is not None and case.assigned_to != assigned_to:
        return False

    requires_review = filters.get("requires_review")
    if requires_review is not None and bool(case.requires_review) != bool(requires_review):
        return False

    query = str(filters.get("q") or filters.get("search") or "").strip().lower()
    if query and query not in case.case_id.lower() and query not in case.title.lower() and query not in case.description.lower():
        return False

    date_from = filters.get("date_from")
    if date_from and _parse_timestamp(case.created_at) < _parse_timestamp(str(date_from)):
        return False

    date_to = filters.get("date_to")
    if date_to and _parse_timestamp(case.created_at) > _parse_timestamp(str(date_to)):
        return False

    return True


class CaseRepository(ABC):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_case_management_config()
        self._config = dict(self._raw_config.get("case_management") or {})
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
    def create_case(self, case: CaseRecord) -> CaseRecord:
        raise NotImplementedError

    @abstractmethod
    def get_case(self, case_id: str) -> CaseRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_cases(self, filters: dict[str, Any] | None = None) -> list[CaseRecord]:
        raise NotImplementedError

    @abstractmethod
    def update_case(self, case_id: str, updates: dict[str, Any]) -> CaseRecord:
        raise NotImplementedError

    @abstractmethod
    def delete_or_archive_case(self, case_id: str) -> CaseRecord:
        raise NotImplementedError

    @abstractmethod
    def add_evidence(self, evidence: CaseEvidence) -> CaseEvidence:
        raise NotImplementedError

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> CaseEvidence | None:
        raise NotImplementedError

    @abstractmethod
    def update_evidence(self, evidence_id: str, updates: dict[str, Any]) -> CaseEvidence:
        raise NotImplementedError

    @abstractmethod
    def list_evidence(self, case_id: str) -> list[CaseEvidence]:
        raise NotImplementedError

    @abstractmethod
    def add_note(self, note: CaseNote) -> CaseNote:
        raise NotImplementedError

    @abstractmethod
    def list_notes(self, case_id: str) -> list[CaseNote]:
        raise NotImplementedError

    @abstractmethod
    def add_audit_log(self, log: CaseAuditLog) -> CaseAuditLog:
        raise NotImplementedError

    @abstractmethod
    def list_audit_logs(self, case_id: str) -> list[CaseAuditLog]:
        raise NotImplementedError

    @abstractmethod
    def add_report(self, export: CaseExport) -> CaseExport:
        raise NotImplementedError

    @abstractmethod
    def list_reports(self, case_id: str) -> list[CaseExport]:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        case_count = len(self.list_cases({})) if self.is_available() else 0
        open_case_count = len(self.list_cases({"status": ["open", "investigating"]})) if self.is_available() else 0
        if not self.enabled:
            status = "disabled"
        elif self.is_available():
            status = "healthy"
        else:
            status = "failed" if _is_production() else "degraded"
        return {
            "enabled": self.enabled,
            "storage": self.storage_backend,
            "status": status,
            "case_count": case_count,
            "open_case_count": open_case_count,
            "last_error": self._last_error,
        }

    def _set_error(self, message: str | None) -> None:
        self._last_error = message

    def _require_available(self) -> None:
        if not self.is_available():
            raise RuntimeError(self._last_error or "Case repository is unavailable")


class JsonlCaseRepository(CaseRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        storage_cfg = dict((self._config.get("storage") or {}))
        self._storage_dir = (PROJECT_ROOT / str(storage_cfg.get("jsonl_dir") or "storage/cases")).resolve()
        self._paths = {
            "cases": self._storage_dir / "cases.jsonl",
            "evidence": self._storage_dir / "evidence.jsonl",
            "notes": self._storage_dir / "notes.jsonl",
            "audit": self._storage_dir / "audit.jsonl",
            "reports": self._storage_dir / "reports.jsonl",
        }
        self._lock = threading.RLock()
        self._cases: dict[str, CaseRecord] = {}
        self._evidence: dict[str, CaseEvidence] = {}
        self._notes: dict[str, list[CaseNote]] = {}
        self._audit_logs: dict[str, list[CaseAuditLog]] = {}
        self._reports: dict[str, list[CaseExport]] = {}
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

    def create_case(self, case: CaseRecord) -> CaseRecord:
        self._require_available()
        with self._lock:
            self._cases[case.case_id] = case
            self._append(self._paths["cases"], case.model_dump(mode="json"))
        return case

    def get_case(self, case_id: str) -> CaseRecord | None:
        with self._lock:
            return self._cases.get(case_id)

    def list_cases(self, filters: dict[str, Any] | None = None) -> list[CaseRecord]:
        filters = filters or {}
        with self._lock:
            items = list(self._cases.values())
        items = [case for case in items if _match_case_filters(case, filters)]
        items.sort(key=lambda item: (_parse_timestamp(item.updated_at), _parse_timestamp(item.created_at)), reverse=True)
        limit = int(filters.get("limit") or 200)
        return items[: max(1, limit)]

    def update_case(self, case_id: str, updates: dict[str, Any]) -> CaseRecord:
        self._require_available()
        with self._lock:
            existing = self._cases.get(case_id)
            if existing is None:
                raise KeyError(case_id)
            payload = existing.model_dump(mode="json")
            payload.update({key: value for key, value in updates.items() if value is not None})
            payload["updated_at"] = payload.get("updated_at") or _now_iso()
            case = CaseRecord.model_validate(payload)
            self._cases[case.case_id] = case
            self._append(self._paths["cases"], case.model_dump(mode="json"))
        return case

    def delete_or_archive_case(self, case_id: str) -> CaseRecord:
        return self.update_case(case_id, {"status": "archived", "updated_at": _now_iso(), "closed_at": _now_iso()})

    def add_evidence(self, evidence: CaseEvidence) -> CaseEvidence:
        self._require_available()
        with self._lock:
            self._evidence[evidence.evidence_id] = evidence
            self._append(self._paths["evidence"], evidence.model_dump(mode="json"))
        return evidence

    def get_evidence(self, evidence_id: str) -> CaseEvidence | None:
        with self._lock:
            return self._evidence.get(evidence_id)

    def update_evidence(self, evidence_id: str, updates: dict[str, Any]) -> CaseEvidence:
        self._require_available()
        with self._lock:
            existing = self._evidence.get(evidence_id)
            if existing is None:
                raise KeyError(evidence_id)
            payload = existing.model_dump(mode="json")
            payload.update({key: value for key, value in updates.items() if value is not None})
            evidence = CaseEvidence.model_validate(payload)
            self._evidence[evidence_id] = evidence
            self._append(self._paths["evidence"], evidence.model_dump(mode="json"))
        return evidence

    def list_evidence(self, case_id: str) -> list[CaseEvidence]:
        with self._lock:
            items = [item for item in self._evidence.values() if item.case_id == case_id]
        items.sort(key=lambda item: (_parse_timestamp(item.timestamp), _parse_timestamp(item.created_at)))
        return items

    def add_note(self, note: CaseNote) -> CaseNote:
        self._require_available()
        with self._lock:
            self._notes.setdefault(note.case_id, []).append(note)
            self._append(self._paths["notes"], note.model_dump(mode="json"))
        return note

    def list_notes(self, case_id: str) -> list[CaseNote]:
        with self._lock:
            items = list(self._notes.get(case_id, []))
        items.sort(key=lambda item: _parse_timestamp(item.created_at))
        return items

    def add_audit_log(self, log: CaseAuditLog) -> CaseAuditLog:
        self._require_available()
        with self._lock:
            self._audit_logs.setdefault(log.case_id, []).append(log)
            self._append(self._paths["audit"], log.model_dump(mode="json"))
        return log

    def list_audit_logs(self, case_id: str) -> list[CaseAuditLog]:
        with self._lock:
            items = list(self._audit_logs.get(case_id, []))
        items.sort(key=lambda item: _parse_timestamp(item.timestamp))
        return items

    def add_report(self, export: CaseExport) -> CaseExport:
        self._require_available()
        with self._lock:
            self._reports.setdefault(export.case_id, []).append(export)
            self._append(self._paths["reports"], export.model_dump(mode="json"))
        return export

    def list_reports(self, case_id: str) -> list[CaseExport]:
        with self._lock:
            items = list(self._reports.get(case_id, []))
        items.sort(key=lambda item: _parse_timestamp(item.generated_at))
        return items

    def _append(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def _load_all(self) -> None:
        loaders = {
            "cases": (CaseRecord, self._cases, None),
            "evidence": (CaseEvidence, self._evidence, "evidence_id"),
            "notes": (CaseNote, self._notes, "case_id"),
            "audit": (CaseAuditLog, self._audit_logs, "case_id"),
            "reports": (CaseExport, self._reports, "case_id"),
        }
        for name, (model_cls, target, grouping_key) in loaders.items():
            path = self._paths[name]
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = model_cls.model_validate(json.loads(line))
                    except Exception:
                        continue
                    if grouping_key is None:
                        target[obj.case_id] = obj
                    elif name == "evidence":
                        target[getattr(obj, grouping_key)] = obj
                    else:
                        target.setdefault(getattr(obj, grouping_key), []).append(obj)


class PostgresCaseRepository(CaseRepository):
    _DDL = """
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        severity TEXT NOT NULL,
        source_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        camera_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        track_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        assigned_to TEXT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        closed_at TIMESTAMPTZ NULL,
        tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        requires_review BOOLEAN NOT NULL DEFAULT TRUE,
        review_status TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS case_evidence (
        evidence_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        evidence_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        source_event_id TEXT NULL,
        camera_id TEXT NULL,
        track_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        storage_uri TEXT NULL,
        snapshot_uri TEXT NULL,
        original_filename TEXT NULL,
        safe_filename TEXT NULL,
        content_type TEXT NULL,
        size_bytes BIGINT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        hash_sha256 TEXT NULL,
        hash_verified BOOLEAN NULL,
        integrity_status TEXT NOT NULL,
        chain_status TEXT NOT NULL DEFAULT 'active',
        last_verified_at TIMESTAMPTZ NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS case_notes (
        note_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        note TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS case_audit (
        audit_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        detail TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE TABLE IF NOT EXISTS case_reports (
        export_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        format TEXT NOT NULL,
        report_type TEXT NOT NULL DEFAULT 'case_export',
        content TEXT NOT NULL,
        generated_at TIMESTAMPTZ NOT NULL,
        generated_by TEXT NOT NULL,
        artifact_uri TEXT NULL,
        content_type TEXT NULL,
        size_bytes BIGINT NULL,
        hash_sha256 TEXT NULL,
        hash_verified BOOLEAN NULL,
        integrity_status TEXT NOT NULL DEFAULT 'pending',
        last_verified_at TIMESTAMPTZ NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        storage_cfg = dict((self._config.get("storage") or {}))
        self._required = bool(storage_cfg.get("require_postgres_in_production", True))
        self._dsn = (
            os.getenv("POSTGRES_DSN")
            or os.getenv("AEGIS_POSTGRES_DSN")
            or os.getenv("DB_URL")
        )
        self._lock = threading.RLock()
        self._available = False
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def create_case(self, case: CaseRecord) -> CaseRecord:
        self._require_available()
        query = """
            INSERT INTO cases (
                case_id, title, description, status, priority, severity,
                source_event_ids, camera_ids, track_ids, assigned_to,
                created_by, created_at, updated_at, closed_at, tags,
                requires_review, review_status, metadata
            ) VALUES (
                %(case_id)s, %(title)s, %(description)s, %(status)s, %(priority)s, %(severity)s,
                %(source_event_ids)s, %(camera_ids)s, %(track_ids)s, %(assigned_to)s,
                %(created_by)s, %(created_at)s, %(updated_at)s, %(closed_at)s, %(tags)s,
                %(requires_review)s, %(review_status)s, %(metadata)s
            )
        """
        self._execute(query, self._case_params(case))
        return case

    def get_case(self, case_id: str) -> CaseRecord | None:
        self._require_available()
        row = self._fetchone("SELECT * FROM cases WHERE case_id = %(case_id)s", {"case_id": case_id})
        return CaseRecord.model_validate(dict(row)) if row else None

    def list_cases(self, filters: dict[str, Any] | None = None) -> list[CaseRecord]:
        self._require_available()
        rows = self._fetchall("SELECT * FROM cases ORDER BY updated_at DESC")
        items = [CaseRecord.model_validate(dict(row)) for row in rows]
        filters = filters or {}
        items = [case for case in items if _match_case_filters(case, filters)]
        limit = int(filters.get("limit") or 200)
        return items[: max(1, limit)]

    def update_case(self, case_id: str, updates: dict[str, Any]) -> CaseRecord:
        self._require_available()
        existing = self.get_case(case_id)
        if existing is None:
            raise KeyError(case_id)
        payload = existing.model_dump(mode="json")
        payload.update({key: value for key, value in updates.items() if value is not None})
        case = CaseRecord.model_validate(payload)
        query = """
            UPDATE cases
            SET title = %(title)s,
                description = %(description)s,
                status = %(status)s,
                priority = %(priority)s,
                severity = %(severity)s,
                source_event_ids = %(source_event_ids)s,
                camera_ids = %(camera_ids)s,
                track_ids = %(track_ids)s,
                assigned_to = %(assigned_to)s,
                created_by = %(created_by)s,
                created_at = %(created_at)s,
                updated_at = %(updated_at)s,
                closed_at = %(closed_at)s,
                tags = %(tags)s,
                requires_review = %(requires_review)s,
                review_status = %(review_status)s,
                metadata = %(metadata)s
            WHERE case_id = %(case_id)s
        """
        self._execute(query, self._case_params(case))
        return case

    def delete_or_archive_case(self, case_id: str) -> CaseRecord:
        return self.update_case(case_id, {"status": "archived", "updated_at": _now_iso(), "closed_at": _now_iso()})

    def add_evidence(self, evidence: CaseEvidence) -> CaseEvidence:
        self._require_available()
        query = """
            INSERT INTO case_evidence (
                evidence_id, case_id, evidence_type, title, description, source_event_id,
                camera_id, track_ids, storage_uri, snapshot_uri, original_filename, safe_filename,
                content_type, size_bytes, created_by, created_at, timestamp, hash_sha256,
                hash_verified, integrity_status, chain_status, last_verified_at, metadata
            ) VALUES (
                %(evidence_id)s, %(case_id)s, %(evidence_type)s, %(title)s, %(description)s, %(source_event_id)s,
                %(camera_id)s, %(track_ids)s, %(storage_uri)s, %(snapshot_uri)s, %(original_filename)s, %(safe_filename)s,
                %(content_type)s, %(size_bytes)s, %(created_by)s, %(created_at)s, %(timestamp)s, %(hash_sha256)s,
                %(hash_verified)s, %(integrity_status)s, %(chain_status)s, %(last_verified_at)s, %(metadata)s
            )
        """
        self._execute(query, self._evidence_params(evidence))
        return evidence

    def get_evidence(self, evidence_id: str) -> CaseEvidence | None:
        self._require_available()
        row = self._fetchone("SELECT * FROM case_evidence WHERE evidence_id = %(evidence_id)s", {"evidence_id": evidence_id})
        return CaseEvidence.model_validate(dict(row)) if row else None

    def update_evidence(self, evidence_id: str, updates: dict[str, Any]) -> CaseEvidence:
        self._require_available()
        existing = self.get_evidence(evidence_id)
        if existing is None:
            raise KeyError(evidence_id)
        payload = existing.model_dump(mode="json")
        payload.update({key: value for key, value in updates.items() if value is not None})
        evidence = CaseEvidence.model_validate(payload)
        query = """
            UPDATE case_evidence
            SET case_id = %(case_id)s,
                evidence_type = %(evidence_type)s,
                title = %(title)s,
                description = %(description)s,
                source_event_id = %(source_event_id)s,
                camera_id = %(camera_id)s,
                track_ids = %(track_ids)s,
                storage_uri = %(storage_uri)s,
                snapshot_uri = %(snapshot_uri)s,
                original_filename = %(original_filename)s,
                safe_filename = %(safe_filename)s,
                content_type = %(content_type)s,
                size_bytes = %(size_bytes)s,
                created_by = %(created_by)s,
                created_at = %(created_at)s,
                timestamp = %(timestamp)s,
                hash_sha256 = %(hash_sha256)s,
                hash_verified = %(hash_verified)s,
                integrity_status = %(integrity_status)s,
                chain_status = %(chain_status)s,
                last_verified_at = %(last_verified_at)s,
                metadata = %(metadata)s
            WHERE evidence_id = %(evidence_id)s
        """
        self._execute(query, self._evidence_params(evidence))
        return evidence

    def list_evidence(self, case_id: str) -> list[CaseEvidence]:
        self._require_available()
        rows = self._fetchall(
            "SELECT * FROM case_evidence WHERE case_id = %(case_id)s ORDER BY timestamp ASC, created_at ASC",
            {"case_id": case_id},
        )
        return [CaseEvidence.model_validate(dict(row)) for row in rows]

    def add_note(self, note: CaseNote) -> CaseNote:
        self._require_available()
        query = """
            INSERT INTO case_notes (note_id, case_id, note, created_by, created_at, metadata)
            VALUES (%(note_id)s, %(case_id)s, %(note)s, %(created_by)s, %(created_at)s, %(metadata)s)
        """
        self._execute(query, self._note_params(note))
        return note

    def list_notes(self, case_id: str) -> list[CaseNote]:
        self._require_available()
        rows = self._fetchall(
            "SELECT * FROM case_notes WHERE case_id = %(case_id)s ORDER BY created_at ASC",
            {"case_id": case_id},
        )
        return [CaseNote.model_validate(dict(row)) for row in rows]

    def add_audit_log(self, log: CaseAuditLog) -> CaseAuditLog:
        self._require_available()
        query = """
            INSERT INTO case_audit (audit_id, case_id, action, actor, timestamp, detail, metadata)
            VALUES (%(audit_id)s, %(case_id)s, %(action)s, %(actor)s, %(timestamp)s, %(detail)s, %(metadata)s)
        """
        self._execute(query, self._audit_params(log))
        return log

    def list_audit_logs(self, case_id: str) -> list[CaseAuditLog]:
        self._require_available()
        rows = self._fetchall(
            "SELECT * FROM case_audit WHERE case_id = %(case_id)s ORDER BY timestamp ASC",
            {"case_id": case_id},
        )
        return [CaseAuditLog.model_validate(dict(row)) for row in rows]

    def add_report(self, export: CaseExport) -> CaseExport:
        self._require_available()
        query = """
            INSERT INTO case_reports (
                export_id, case_id, format, report_type, content, generated_at, generated_by,
                artifact_uri, content_type, size_bytes, hash_sha256, hash_verified,
                integrity_status, last_verified_at, metadata
            )
            VALUES (
                %(export_id)s, %(case_id)s, %(format)s, %(report_type)s, %(content)s, %(generated_at)s, %(generated_by)s,
                %(artifact_uri)s, %(content_type)s, %(size_bytes)s, %(hash_sha256)s, %(hash_verified)s,
                %(integrity_status)s, %(last_verified_at)s, %(metadata)s
            )
        """
        self._execute(query, self._report_params(export))
        return export

    def list_reports(self, case_id: str) -> list[CaseExport]:
        self._require_available()
        rows = self._fetchall(
            "SELECT * FROM case_reports WHERE case_id = %(case_id)s ORDER BY generated_at ASC",
            {"case_id": case_id},
        )
        return [CaseExport.model_validate(dict(row)) for row in rows]

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._available = False
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._available = False
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    for statement in [part.strip() for part in self._DDL.split(";") if part.strip()]:
                        cursor.execute(statement)
                    for statement in (
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS original_filename TEXT NULL",
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS safe_filename TEXT NULL",
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS content_type TEXT NULL",
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS size_bytes BIGINT NULL",
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS chain_status TEXT NOT NULL DEFAULT 'active'",
                        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ NULL",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS report_type TEXT NOT NULL DEFAULT 'case_export'",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS content_type TEXT NULL",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS size_bytes BIGINT NULL",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS hash_sha256 TEXT NULL",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS hash_verified BOOLEAN NULL",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS integrity_status TEXT NOT NULL DEFAULT 'pending'",
                        "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ NULL",
                    ):
                        cursor.execute(statement)
                conn.commit()
            self._available = True
            self._set_error(None)
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))
            if _is_production() and self._required:
                return

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
            _record_repo_latency((time.monotonic() - started) * 1000.0)

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
            _record_repo_latency((time.monotonic() - started) * 1000.0)

    def _fetchall(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        started = time.monotonic()
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params or {})
                    rows = cursor.fetchall()
            self._available = True
            self._set_error(None)
            return rows
        except Exception as exc:
            self._available = False
            self._set_error(str(exc))
            raise
        finally:
            _record_repo_latency((time.monotonic() - started) * 1000.0)

    @staticmethod
    def _case_params(case: CaseRecord) -> dict[str, Any]:
        return {
            **case.model_dump(mode="json"),
            "source_event_ids": Json(case.source_event_ids),
            "camera_ids": Json(case.camera_ids),
            "track_ids": Json(case.track_ids),
            "tags": Json(case.tags),
            "metadata": Json(case.metadata),
        }

    @staticmethod
    def _evidence_params(evidence: CaseEvidence) -> dict[str, Any]:
        return {
            **evidence.model_dump(mode="json"),
            "track_ids": Json(evidence.track_ids),
            "metadata": Json(evidence.metadata),
        }

    @staticmethod
    def _note_params(note: CaseNote) -> dict[str, Any]:
        return {**note.model_dump(mode="json"), "metadata": Json(note.metadata)}

    @staticmethod
    def _audit_params(log: CaseAuditLog) -> dict[str, Any]:
        return {**log.model_dump(mode="json"), "metadata": Json(log.metadata)}

    @staticmethod
    def _report_params(export: CaseExport) -> dict[str, Any]:
        return {**export.model_dump(mode="json"), "metadata": Json(export.metadata)}


def _record_repo_latency(value_ms: float) -> None:
    rounded = round(max(0.0, value_ms), 2)
    try:
        from inference.monitoring.metrics import get_metrics

        metrics = get_metrics()
        if hasattr(metrics, "record_segmentation_value"):
            metrics.record_segmentation_value("case_repository_latency_ms", rounded)
    except Exception:
        pass
    try:
        from inference.metrics import metrics as system_metrics

        if hasattr(system_metrics, "set_value"):
            system_metrics.set_value("case_repository_latency_ms", rounded)
    except Exception:
        pass


def build_case_repository(config: dict[str, Any] | None = None) -> CaseRepository:
    payload = config or load_case_management_config()
    case_cfg = dict(payload.get("case_management") or {})
    storage_cfg = dict(case_cfg.get("storage") or {})
    if _is_production():
        backend = str(storage_cfg.get("production_backend") or "postgres").lower()
        if backend == "postgres":
            return PostgresCaseRepository(config=payload)
        return JsonlCaseRepository(config=payload)
    return JsonlCaseRepository(config=payload)


def get_case_repository() -> CaseRepository:
    global _CASE_REPOSITORY
    if _CASE_REPOSITORY is None:
        with _CASE_REPOSITORY_LOCK:
            if _CASE_REPOSITORY is None:
                _CASE_REPOSITORY = build_case_repository()
    return _CASE_REPOSITORY


def set_case_repository(repository: CaseRepository) -> None:
    global _CASE_REPOSITORY
    with _CASE_REPOSITORY_LOCK:
        _CASE_REPOSITORY = repository


def reset_case_repository() -> None:
    global _CASE_REPOSITORY
    with _CASE_REPOSITORY_LOCK:
        _CASE_REPOSITORY = None
