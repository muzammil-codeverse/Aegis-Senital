from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.persistence import (
    RepositoryHealth,
    get_store_backend,
    is_production_environment,
    postgres_dsn,
    prohibit_jsonl_fallback,
    store_required_in_production,
)
from app.db.schema_bootstrap import bootstrap_schema

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except Exception:  # pragma: no cover - optional dependency in some test environments
    psycopg2 = None
    Json = None
    RealDictCursor = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class IdentityRepository(ABC):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._last_error: str | None = None

    @property
    @abstractmethod
    def storage_backend(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def upsert_global_identity(self, record: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_global_identity(self, global_identity_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_global_identities(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def append_observation(self, observation: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_observations(self, *, global_identity_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def append_enrollment(self, enrollment: dict[str, Any]) -> None:
        raise NotImplementedError

    def health_check(self) -> RepositoryHealth:
        if self.is_available():
            status = "healthy"
        else:
            status = "failed" if is_production_environment() else "degraded"
        return RepositoryHealth(
            store="identity_registry",
            backend=self.storage_backend,
            status=status,
            last_error=self._last_error,
        )

    def _set_error(self, message: str | None) -> None:
        self._last_error = message


class JsonlIdentityRepository(IdentityRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._store_dir = Path(str((config or {}).get("store_dir") or PROJECT_ROOT / "storage" / "identities"))
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._store_dir / "global_identity_registry.jsonl"
        self._observations_path = self._store_dir / "global_identity_observations.jsonl"
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._observations: list[dict[str, Any]] = []
        try:
            self._load()
            self._set_error(None)
        except Exception as exc:
            self._set_error(str(exc))

    @property
    def storage_backend(self) -> str:
        return "jsonl"

    def is_available(self) -> bool:
        return self._last_error is None and os.access(str(self._store_dir), os.W_OK)

    def health_check(self) -> RepositoryHealth:
        health = super().health_check()
        if (
            is_production_environment()
            and store_required_in_production("identity_registry")
            and prohibit_jsonl_fallback()
        ):
            health.status = "failed"
            health.last_error = health.last_error or "JSONL fallback is prohibited for the identity registry in production"
        return health

    def upsert_global_identity(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._records[str(record["global_identity_id"])] = dict(record)
            self._rewrite_registry()

    def get_global_identity(self, global_identity_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(global_identity_id)
            return dict(record) if record is not None else None

    def list_global_identities(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._records.values())
        if status:
            items = [item for item in items if str(item.get("status") or "") == status]
        items.sort(key=lambda item: str(item.get("last_seen") or ""), reverse=True)
        return [dict(item) for item in items[: max(1, limit)]]

    def append_observation(self, observation: dict[str, Any]) -> None:
        with self._lock:
            self._observations.append(dict(observation))
            with self._observations_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(observation, sort_keys=True) + "\n")

    def list_observations(self, *, global_identity_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._observations)
        if global_identity_id:
            items = [item for item in items if str(item.get("global_identity_id") or "") == str(global_identity_id)]
        items.sort(key=lambda item: str(item.get("observed_at") or ""), reverse=True)
        return [dict(item) for item in items[: max(1, limit)]]

    def append_enrollment(self, enrollment: dict[str, Any]) -> None:
        # Development JSONL already persists enrollments through IdentityProfileStore.
        del enrollment

    def _load(self) -> None:
        if self._registry_path.exists():
            with self._registry_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    self._records[str(payload["global_identity_id"])] = payload
        if self._observations_path.exists():
            with self._observations_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    self._observations.append(json.loads(line))

    def _rewrite_registry(self) -> None:
        tmp = self._registry_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for item in self._records.values():
                handle.write(json.dumps(item, sort_keys=True) + "\n")
        tmp.replace(self._registry_path)


class PostgresIdentityRepository(IdentityRepository):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self._dsn = postgres_dsn()
        self._available = False
        self._initialize()

    @property
    def storage_backend(self) -> str:
        return "postgres"

    def is_available(self) -> bool:
        return self._available

    def upsert_global_identity(self, record: dict[str, Any]) -> None:
        self._require_available()
        query = """
            INSERT INTO global_identity_links (
                global_identity_id, status, confidence, first_seen, last_seen,
                last_source_id, last_camera_id, observation_count, confidence_history,
                source_scores, camera_observations, cameras_seen, ttl_expires_at,
                decay_metadata, operator_review_status, linked_case_ids, metadata,
                created_at, updated_at
            )
            VALUES (
                %(global_identity_id)s, %(status)s, %(confidence)s, %(first_seen)s, %(last_seen)s,
                %(last_source_id)s, %(last_camera_id)s, %(observation_count)s, %(confidence_history)s,
                %(source_scores)s, %(camera_observations)s, %(cameras_seen)s, %(ttl_expires_at)s,
                %(decay_metadata)s, %(operator_review_status)s, %(linked_case_ids)s, %(metadata)s,
                %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (global_identity_id) DO UPDATE SET
                status = EXCLUDED.status,
                confidence = EXCLUDED.confidence,
                first_seen = EXCLUDED.first_seen,
                last_seen = EXCLUDED.last_seen,
                last_source_id = EXCLUDED.last_source_id,
                last_camera_id = EXCLUDED.last_camera_id,
                observation_count = EXCLUDED.observation_count,
                confidence_history = EXCLUDED.confidence_history,
                source_scores = EXCLUDED.source_scores,
                camera_observations = EXCLUDED.camera_observations,
                cameras_seen = EXCLUDED.cameras_seen,
                ttl_expires_at = EXCLUDED.ttl_expires_at,
                decay_metadata = EXCLUDED.decay_metadata,
                operator_review_status = EXCLUDED.operator_review_status,
                linked_case_ids = EXCLUDED.linked_case_ids,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
        """
        self._execute(
            query,
            {
                **record,
                "confidence_history": Json(record.get("confidence_history") or []),
                "source_scores": Json(record.get("source_scores") or {}),
                "camera_observations": Json(record.get("camera_observations") or {}),
                "cameras_seen": Json(record.get("cameras_seen") or []),
                "decay_metadata": Json(record.get("decay_metadata") or {}),
                "linked_case_ids": Json(record.get("linked_case_ids") or []),
                "metadata": Json(record.get("metadata") or {}),
            },
        )

    def get_global_identity(self, global_identity_id: str) -> dict[str, Any] | None:
        self._require_available()
        row = self._fetchone(
            "SELECT * FROM global_identity_links WHERE global_identity_id = %(global_identity_id)s",
            {"global_identity_id": global_identity_id},
        )
        return dict(row) if row else None

    def list_global_identities(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        self._require_available()
        if status:
            query = """
                SELECT * FROM global_identity_links
                WHERE status = %(status)s
                ORDER BY last_seen DESC
                LIMIT %(limit)s
            """
            params = {"status": status, "limit": max(1, limit)}
        else:
            query = """
                SELECT * FROM global_identity_links
                ORDER BY last_seen DESC
                LIMIT %(limit)s
            """
            params = {"limit": max(1, limit)}
        return [dict(row) for row in self._fetchall(query, params)]

    def append_observation(self, observation: dict[str, Any]) -> None:
        self._require_available()
        query = """
            INSERT INTO identity_observations (
                observation_id, global_identity_id, source_track_id, source_camera_id, source_type,
                observed_at, confidence, face_score, reid_score, track_score, source_scores,
                metadata, created_at
            )
            VALUES (
                %(observation_id)s, %(global_identity_id)s, %(source_track_id)s, %(source_camera_id)s, %(source_type)s,
                %(observed_at)s, %(confidence)s, %(face_score)s, %(reid_score)s, %(track_score)s, %(source_scores)s,
                %(metadata)s, %(created_at)s
            )
        """
        self._execute(
            query,
            {
                **observation,
                "source_scores": Json(observation.get("source_scores") or {}),
                "metadata": Json(observation.get("metadata") or {}),
            },
        )

    def list_observations(self, *, global_identity_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        self._require_available()
        params: dict[str, Any] = {"limit": max(1, limit)}
        query = """
            SELECT * FROM identity_observations
        """
        if global_identity_id:
            query += " WHERE global_identity_id = %(global_identity_id)s"
            params["global_identity_id"] = global_identity_id
        query += " ORDER BY observed_at DESC LIMIT %(limit)s"
        return [dict(row) for row in self._fetchall(query, params)]

    def append_enrollment(self, enrollment: dict[str, Any]) -> None:
        self._require_available()
        query = """
            INSERT INTO identity_enrollments (
                enrollment_id, identity_id, image_ref, embedding_vector_ref, quality_score,
                status, rejection_reasons, quality_metrics, source_breakdown,
                batch_enrollment_id, metadata, created_at
            )
            VALUES (
                %(enrollment_id)s, %(identity_id)s, %(image_ref)s, %(embedding_vector_ref)s, %(quality_score)s,
                %(status)s, %(rejection_reasons)s, %(quality_metrics)s, %(source_breakdown)s,
                %(batch_enrollment_id)s, %(metadata)s, %(created_at)s
            )
            ON CONFLICT (enrollment_id) DO NOTHING
        """
        params = {
            **enrollment,
            "rejection_reasons": Json(enrollment.get("rejection_reasons") or []),
            "quality_metrics": Json(enrollment.get("quality_metrics") or {}),
            "source_breakdown": Json(enrollment.get("source_breakdown") or {}),
            "metadata": Json(enrollment.get("metadata") or {}),
        }
        self._execute(query, params)

    def _initialize(self) -> None:
        if psycopg2 is None:
            self._set_error("psycopg2 is not installed")
            return
        if not self._dsn:
            self._set_error("POSTGRES_DSN is not configured")
            return
        try:
            with self._connect() as conn:
                bootstrap_schema(conn, ("identity_enrollments", "identity_observations", "global_identity_links", "watchlists"))
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

    def _fetchone(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        self._available = True
        self._set_error(None)
        return row

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        self._available = True
        self._set_error(None)
        return rows

    def _require_available(self) -> None:
        if not self.is_available():
            raise RuntimeError(self._last_error or "Identity repository is unavailable")


def build_identity_repository(config: dict[str, Any] | None = None) -> IdentityRepository:
    backend = get_store_backend("identity_registry", default_dev="jsonl", default_prod="postgres").lower()
    if is_production_environment() and backend == "postgres":
        return PostgresIdentityRepository(config=config)
    return JsonlIdentityRepository(config=config)
