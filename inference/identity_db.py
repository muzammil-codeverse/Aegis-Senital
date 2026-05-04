from __future__ import annotations

import logging
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inference.db import PostgresManager, VectorStore
from ml.runtime import system_boot_check

logger = logging.getLogger(__name__)

SCENARIO_ACTIVE = "ACTIVE"
SCENARIO_ESCALATING = "ESCALATING"
SCENARIO_RESOLVED = "RESOLVED"
SCENARIO_FALSE_ALARM = "FALSE_ALARM"

_VALID_STATUSES = {
    SCENARIO_ACTIVE,
    SCENARIO_ESCALATING,
    SCENARIO_RESOLVED,
    SCENARIO_FALSE_ALARM,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_embedding(embedding: list[float] | None) -> bool:
    return bool(embedding and len(embedding) > 0)


class IdentityDB:
    """
    Strict identity/event/scenario adapter backed by FAISS and PostgreSQL.
    """

    def __init__(self, db_path: Path | str | None = None, postgres_dsn: str | None = None) -> None:
        system_boot_check()
        self._db_path = Path(db_path) if db_path else None
        self._postgres = PostgresManager(dsn=postgres_dsn)
        self._vectors = VectorStore(dim=512)
        logger.info("IdentityDB initialised with mandatory PostgreSQL and FAISS backends.")

    @property
    def vector_store(self) -> VectorStore:
        return self._vectors

    @property
    def db_healthy(self) -> bool:
        return self._postgres.healthy

    def insert_track(self, track: Any) -> str:
        identity_id = getattr(track, "identity_id", None) or getattr(track, "persistent_track_id", None)
        if identity_id is None:
            identity_id = str(uuid.uuid4())
            if hasattr(track, "identity_id"):
                track.identity_id = identity_id
        if getattr(track, "persistent_track_id", None) is None and hasattr(track, "persistent_track_id"):
            track.persistent_track_id = identity_id
        if getattr(track, "track_uuid", None) is None and hasattr(track, "track_uuid"):
            track.track_uuid = str(uuid.uuid4())
        if hasattr(track, "last_seen_at"):
            track.last_seen_at = getattr(track, "last_seen_at", None) or _now_iso()
        if hasattr(track, "first_seen_at"):
            track.first_seen_at = getattr(track, "first_seen_at", None) or _now_iso()

        self.persist_identity(
            identity_id=identity_id,
            face_embedding=getattr(track, "face_embedding", None),
            appearance_embedding=getattr(track, "appearance_embedding", None),
            metadata={
                "class_name": getattr(track, "class_name", None),
                "camera_id": getattr(track, "camera_id", "default"),
                "track_id": getattr(track, "track_id", None),
            },
        )
        self._postgres.upsert_track(self._build_track_record(track))
        return identity_id

    def update_track(self, track_id: int, **updates: Any) -> None:
        record = self._postgres.query_track_history(track_id)
        if record is None:
            return
        record.update(deepcopy(updates))
        record["last_seen"] = updates.get("last_seen", _now_iso())
        self._postgres.upsert_track(record)

    def query_track_history(self, track_id: int | str) -> dict | None:
        return self._postgres.query_track_history(track_id)

    def persist_identity(
        self,
        *,
        identity_id: str,
        face_embedding: list[float] | None = None,
        appearance_embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not _has_embedding(face_embedding) or not _has_embedding(appearance_embedding):
            logger.debug(
                "persist_identity: skipping FAISS upsert for %s — embeddings unavailable (degraded mode).",
                identity_id,
            )
            return
        self._vectors.upsert_identity(
            identity_id,
            face_embedding=face_embedding,
            appearance_embedding=appearance_embedding,
            metadata=metadata,
        )

    def search_top_k(
        self,
        embedding: list[float] | None,
        k: int = 5,
        *,
        modality: str = "appearance",
    ) -> list[dict[str, Any]]:
        if not _has_embedding(embedding):
            return []
        return self._vectors.search_top_k(embedding, k=k, modality=modality)

    def resolve_identity_candidates(
        self,
        *,
        face_embedding: list[float] | None = None,
        appearance_embedding: list[float] | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        if not _has_embedding(face_embedding) or not _has_embedding(appearance_embedding):
            return []
        merged: dict[str, dict[str, Any]] = {}
        for hit in self.search_top_k(face_embedding, k=k, modality="face"):
            merged.setdefault(
                hit["identity_id"],
                {"identity_id": hit["identity_id"], "face_score": 0.0, "appearance_score": 0.0},
            )["face_score"] = float(hit["score"])
        for hit in self.search_top_k(appearance_embedding, k=k, modality="appearance"):
            merged.setdefault(
                hit["identity_id"],
                {"identity_id": hit["identity_id"], "face_score": 0.0, "appearance_score": 0.0},
            )["appearance_score"] = float(hit["score"])
            merged[hit["identity_id"]]["metadata"] = deepcopy(hit.get("metadata", {}))

        results = []
        for identity_id, payload in merged.items():
            combined = 0.5 * payload["face_score"] + 0.3 * payload["appearance_score"]
            results.append(
                {
                    **payload,
                    "identity_id": identity_id,
                    "combined_score": round(combined, 4),
                }
            )
        results.sort(key=lambda row: row["combined_score"], reverse=True)
        return results[:k]

    def persist_event(self, event: Any, frame_id: int = 0) -> None:
        track_ref_ids = list(getattr(event, "track_ref_ids", []) or [])
        record = {
            "event_id": getattr(event, "event_id", str(uuid.uuid4())),
            "track_id": track_ref_ids[0] if track_ref_ids else None,
            "event_type": getattr(event, "event_type", "UNKNOWN"),
            "confidence": float(getattr(event, "confidence_score", 0.0)),
            "risk_score": float(getattr(event, "risk_score", getattr(event, "severity_score", 0.0))),
            "timestamp": getattr(event, "timestamp", _now_iso()),
            "severity": getattr(event, "severity", "LOW"),
            "metadata": {
                "frame_id": frame_id,
                "track_ids": list(getattr(event, "track_ids", [])),
                "track_ref_ids": track_ref_ids,
                "identity_ids": list(getattr(event, "identity_ids", [])),
                "camera_ids": list(getattr(event, "camera_ids", [])),
                "payload": event.to_dict() if hasattr(event, "to_dict") else deepcopy(event),
            },
        }
        self._postgres.insert_event(record)
        if hasattr(event, "persisted"):
            event.persisted = True

    def get_active_threats(self, limit: int = 50) -> list[dict]:
        return self._postgres.get_active_threats(limit)

    def get_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self._postgres.get_events(event_type=event_type, severity=severity, limit=limit)

    def persist_scenario(self, scenario: Any) -> None:
        record = {
            "scenario_id": getattr(scenario, "scenario_id", str(uuid.uuid4())),
            "event_cluster": [
                event.to_dict() if hasattr(event, "to_dict") else deepcopy(event)
                for event in getattr(scenario, "event_cluster", getattr(scenario, "events", []))
            ],
            "scenario_type": getattr(scenario, "scenario_type", "NORMAL_ACTIVITY"),
            "risk_level": getattr(scenario, "risk_level", "LOW"),
            "status": getattr(scenario, "status", SCENARIO_ACTIVE),
            "start_time": getattr(scenario, "start_time", _now_iso()),
            "end_time": getattr(scenario, "end_time", None),
            "metadata": {
                "summary": getattr(scenario, "summary", ""),
                "confidence_score": getattr(scenario, "confidence_score", 0.0),
                "camera_ids": list(getattr(scenario, "camera_ids", [])),
                "identity_ids": list(getattr(scenario, "identity_ids", [])),
                "payload": scenario.to_dict() if hasattr(scenario, "to_dict") else deepcopy(scenario),
            },
        }
        self._postgres.insert_scenario(record)
        if hasattr(scenario, "persisted"):
            scenario.persisted = True

    def update_scenario_status(
        self,
        scenario_id: str,
        status: str,
        end_time: str | None = None,
    ) -> None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Valid: {_VALID_STATUSES}")
        resolved_time = end_time or (_now_iso() if status in {SCENARIO_RESOLVED, SCENARIO_FALSE_ALARM} else None)
        self._postgres.update_scenario_status(scenario_id, status, resolved_time)

    def get_scenarios(self, status: str | None = None, limit: int = 50) -> list[dict]:
        return self._postgres.get_scenarios(status=status, limit=limit)

    def get_tracks(self, limit: int = 100) -> list[dict]:
        return self._postgres.fetch_tracks(limit=limit)

    def close(self) -> None:
        self._postgres.close()

    @staticmethod
    def _build_track_record(track: Any) -> dict[str, Any]:
        first_seen = getattr(track, "first_seen_at", None) or _now_iso()
        last_seen = getattr(track, "last_seen_at", None) or first_seen
        return {
            "track_id": getattr(track, "track_uuid", str(uuid.uuid4())),
            "identity_id": getattr(track, "identity_id", None) or getattr(track, "persistent_track_id", None) or str(uuid.uuid4()),
            "local_track_id": getattr(track, "track_id", None),
            "camera_id": getattr(track, "camera_id", "default"),
            "bbox": list(getattr(track, "bbox", [])),
            "start_time": first_seen,
            "last_seen": last_seen,
            "status": getattr(track, "status", "ACTIVE"),
            "class_name": getattr(track, "class_name", None),
            "confidence": float(getattr(track, "confidence", 0.0)),
            "metadata": {
                "missed_frames": getattr(track, "missed_frames", 0),
                "velocity": list(getattr(track, "velocity", [])),
                "stability_score": getattr(track, "stability_score", 0.0),
                "identity_confidence": getattr(track, "identity_confidence", 0.0),
                "face_embedding": list(getattr(track, "face_embedding", [])),
                "appearance_embedding": list(getattr(track, "appearance_embedding", [])),
                "track_payload": track.to_dict() if hasattr(track, "to_dict") else {},
            },
        }


_db: IdentityDB | None = None
_db_lock = threading.Lock()


def get_db(db_path: Path | str | None = None) -> IdentityDB:
    global _db
    with _db_lock:
        if _db is None:
            _db = IdentityDB(db_path)
    return _db


def insert_track(track: Any) -> str:
    return get_db().insert_track(track)


def update_track(track_id: int, **updates: Any) -> None:
    get_db().update_track(track_id, **updates)


def query_track_history(track_id: int | str) -> dict | None:
    return get_db().query_track_history(track_id)


def persist_event(event: Any, frame_id: int = 0) -> None:
    get_db().persist_event(event, frame_id)


def persist_scenario(scenario: Any) -> None:
    get_db().persist_scenario(scenario)


def update_scenario_status(scenario_id: str, status: str) -> None:
    get_db().update_scenario_status(scenario_id, status)


def get_active_threats(limit: int = 50) -> list[dict]:
    return get_db().get_active_threats(limit)
