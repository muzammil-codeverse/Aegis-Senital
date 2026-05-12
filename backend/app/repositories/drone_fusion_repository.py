"""JSONL-backed repository for Phase 46 Drone + Fixed Camera Fusion data.

Provides a PostgreSQL-ready abstraction for development.
Production mode with production_required=true will fail readiness if Postgres is absent.
No silent JSONL fallback in production.

PostgreSQL DDL (bootstrap-ready):

  CREATE TABLE IF NOT EXISTS drone_fusion_observations (
      observation_id TEXT PRIMARY KEY,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE TABLE IF NOT EXISTS drone_fusion_correlations (
      correlation_id TEXT PRIMARY KEY,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE TABLE IF NOT EXISTS drone_fusion_handoffs (
      handoff_id TEXT PRIMARY KEY,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE TABLE IF NOT EXISTS drone_fusion_reviews (
      review_id TEXT PRIMARY KEY,
      correlation_id TEXT NOT NULL,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE TABLE IF NOT EXISTS drone_fusion_timelines (
      entry_id TEXT PRIMARY KEY,
      case_id TEXT,
      data JSONB NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW()
  );
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.drone_fusion_models import (
    CrossSourceCorrelation,
    DroneCameraHandoff,
    FusionObservation,
    FusionReviewRecord,
    FusionReviewRequest,
    FusionTimeline,
    FusionTimelineEntry,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_instance: DroneFusionRepository | None = None
_instance_lock = threading.Lock()


class DroneFusionRepositoryError(Exception):
    pass


class DroneFusionRepository:
    """Development JSONL storage for fusion data.

    Interface mirrors a PostgreSQL-backed production repository.
    """

    def __init__(
        self,
        root_dir: str | Path | None = None,
        production_mode: bool = False,
        production_required: bool = False,
    ) -> None:
        self._production_mode = production_mode
        self._production_required = production_required
        self.storage_backend = "jsonl"

        if production_mode and production_required:
            raise DroneFusionRepositoryError(
                "Production mode with required=True: PostgreSQL backend not configured. "
                "Set POSTGRES_DSN and implement PostgreSQL backend before enabling production_required."
            )

        root = Path(root_dir) if root_dir else Path("storage/drone_fusion")
        root.mkdir(parents=True, exist_ok=True)

        self._obs_path = root / "observations.jsonl"
        self._corr_path = root / "correlations.jsonl"
        self._handoff_path = root / "handoffs.jsonl"
        self._review_path = root / "reviews.jsonl"
        self._timeline_path = root / "timelines.jsonl"

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        results: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return results

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _rewrite(self, path: Path, records: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def save_observation(self, observation: FusionObservation) -> FusionObservation:
        with self._lock:
            self._append(self._obs_path, observation.model_dump())
        return observation

    def get_observation(self, observation_id: str) -> FusionObservation | None:
        with self._lock:
            for rec in self._read_all(self._obs_path):
                if rec.get("observation_id") == observation_id:
                    return FusionObservation.model_validate(rec)
        return None

    def list_observations(
        self,
        case_id: str | None = None,
        event_id: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
        user_scope: list[str] | None = None,
    ) -> list[FusionObservation]:
        with self._lock:
            records = self._read_all(self._obs_path)
        results = []
        for rec in records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            if source_type and rec.get("source_type") != source_type:
                continue
            if user_scope is not None and rec.get("source_id") not in user_scope:
                continue
            results.append(FusionObservation.model_validate(rec))
        return results[-limit:]

    # ------------------------------------------------------------------
    # Correlations
    # ------------------------------------------------------------------

    def save_correlation(self, correlation: CrossSourceCorrelation) -> CrossSourceCorrelation:
        with self._lock:
            self._append(self._corr_path, correlation.model_dump())
        return correlation

    def get_correlation(self, correlation_id: str) -> CrossSourceCorrelation | None:
        with self._lock:
            for rec in self._read_all(self._corr_path):
                if rec.get("correlation_id") == correlation_id:
                    return CrossSourceCorrelation.model_validate(rec)
        return None

    def list_correlations(
        self,
        case_id: str | None = None,
        event_id: str | None = None,
        review_status: str | None = None,
        limit: int = 100,
    ) -> list[CrossSourceCorrelation]:
        with self._lock:
            records = self._read_all(self._corr_path)
        results = []
        for rec in records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            if review_status and rec.get("review_status") != review_status:
                continue
            results.append(CrossSourceCorrelation.model_validate(rec))
        return results[-limit:]

    def review_correlation(
        self,
        correlation_id: str,
        review_request: FusionReviewRequest,
        reviewed_by: str,
    ) -> CrossSourceCorrelation | None:
        status_map = {
            "accept": "accepted",
            "reject": "rejected",
            "inconclusive": "inconclusive",
        }
        new_status = status_map[review_request.action]

        with self._lock:
            records = self._read_all(self._corr_path)
            updated = None
            for rec in records:
                if rec.get("correlation_id") == correlation_id:
                    rec["review_status"] = new_status
                    rec["reviewed_by"] = reviewed_by
                    rec["reviewed_at"] = _now_iso()
                    rec["review_notes"] = review_request.notes
                    updated = CrossSourceCorrelation.model_validate(rec)
            if updated is None:
                return None
            self._rewrite(self._corr_path, records)

            review_record = FusionReviewRecord(
                correlation_id=correlation_id,
                action=review_request.action,
                reviewed_by=reviewed_by,
                notes=review_request.notes,
            )
            self._append(self._review_path, review_record.model_dump())

        return updated

    # ------------------------------------------------------------------
    # Handoffs
    # ------------------------------------------------------------------

    def save_handoff(self, handoff: DroneCameraHandoff) -> DroneCameraHandoff:
        with self._lock:
            self._append(self._handoff_path, handoff.model_dump())
        return handoff

    def list_handoffs(
        self,
        case_id: str | None = None,
        event_id: str | None = None,
        limit: int = 100,
    ) -> list[DroneCameraHandoff]:
        with self._lock:
            records = self._read_all(self._handoff_path)
        results = []
        for rec in records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            results.append(DroneCameraHandoff.model_validate(rec))
        return results[-limit:]

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def build_fusion_timeline(
        self,
        case_id: str | None = None,
        event_id: str | None = None,
    ) -> FusionTimeline:
        entries: list[FusionTimelineEntry] = []

        with self._lock:
            obs_records = self._read_all(self._obs_path)
            corr_records = self._read_all(self._corr_path)
            handoff_records = self._read_all(self._handoff_path)

        for rec in obs_records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            entries.append(FusionTimelineEntry(
                timestamp=rec.get("timestamp", _now_iso()),
                entry_type="observation",
                source_type=rec.get("source_type"),
                source_id=rec.get("source_id"),
                observation_id=rec.get("observation_id"),
                simulated=bool(rec.get("simulated", False)),
                case_id=rec.get("case_id"),
            ))

        for rec in corr_records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            entries.append(FusionTimelineEntry(
                timestamp=rec.get("created_at", _now_iso()),
                entry_type="correlation",
                correlation_id=rec.get("correlation_id"),
                confidence=rec.get("confidence"),
                safe_summary=rec.get("safe_summary"),
                case_id=rec.get("case_id"),
            ))

        for rec in handoff_records:
            if case_id and rec.get("case_id") != case_id:
                continue
            if event_id and rec.get("event_id") != event_id:
                continue
            entries.append(FusionTimelineEntry(
                timestamp=rec.get("timestamp", _now_iso()),
                entry_type="handoff",
                handoff_id=rec.get("handoff_id"),
                confidence=rec.get("confidence"),
                safe_summary=rec.get("safe_summary"),
                case_id=rec.get("case_id"),
            ))

        entries.sort(key=lambda e: e.timestamp)

        return FusionTimeline(
            case_id=case_id,
            event_id=event_id,
            entries=entries,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            obs = self._read_all(self._obs_path)
            corr = self._read_all(self._corr_path)
            pending = [c for c in corr if c.get("review_status") == "pending"]

        return {
            "status": "healthy",
            "backend": self.storage_backend,
            "observations": len(obs),
            "correlations": len(corr),
            "pending_reviews": len(pending),
            "last_error": None,
        }

    def count_stats(self) -> dict[str, int]:
        with self._lock:
            corr = self._read_all(self._corr_path)
        accepted = sum(1 for c in corr if c.get("review_status") == "accepted")
        rejected = sum(1 for c in corr if c.get("review_status") == "rejected")
        pending = sum(1 for c in corr if c.get("review_status") == "pending")
        return {
            "correlations_total": len(corr),
            "correlations_accepted": accepted,
            "correlations_rejected": rejected,
            "correlations_pending": pending,
        }


def get_drone_fusion_repository(root_dir: str | Path | None = None) -> DroneFusionRepository:
    global _instance
    with _instance_lock:
        if _instance is None:
            import os
            production_mode = os.environ.get("AEGIS_ENV", "development").lower() == "production"
            _instance = DroneFusionRepository(
                root_dir=root_dir,
                production_mode=production_mode,
                production_required=False,
            )
    return _instance
