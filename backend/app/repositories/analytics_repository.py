from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.models.analytics_models import AnalyticsTimeRange
from app.repositories.incident_repository import get_incident_repository
from app.services.audit_log_service import get_audit_log_service
from app.services.stream_session_manager import get_stream_session_manager
from app.repositories.case_repository import get_case_repository
from core.event_bus import get_event_bus
from inference.identity.global_identity_registry import get_global_registry
from inference.identity.identity_profile_store import get_identity_store
from inference.identity_db import get_db
from inference.monitoring.metrics import get_metrics
from inference.stream.stream_session_manager import get_runtime_stream_session_manager
from inference.system_state import get_system_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANALYTICS_CONFIG_PATH = PROJECT_ROOT / "configs" / "runtime" / "analytics.yaml"
PRODUCTION_ENVS = {"prod", "production"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment_name() -> str:
    return (os.getenv("APP_ENV") or os.getenv("AEGIS_ENV") or "development").strip().lower()


def _is_production() -> bool:
    return _environment_name() in PRODUCTION_ENVS


def load_analytics_config() -> dict[str, Any]:
    if not ANALYTICS_CONFIG_PATH.exists():
        return {"analytics": {"enabled": False}}
    with ANALYTICS_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid analytics config: {ANALYTICS_CONFIG_PATH}")
    return payload


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dt_to_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _range_bounds(time_range: AnalyticsTimeRange | dict[str, Any]) -> tuple[datetime, datetime]:
    payload = time_range if isinstance(time_range, AnalyticsTimeRange) else AnalyticsTimeRange.model_validate(time_range)
    start = _parse_datetime(payload.start) or datetime.now(timezone.utc)
    end = _parse_datetime(payload.end) or datetime.now(timezone.utc)
    if end < start:
        start, end = end, start
    return start, end


def _match_scalar_filter(value: Any, raw_filter: Any) -> bool:
    if raw_filter is None or raw_filter == "":
        return True
    allowed = raw_filter if isinstance(raw_filter, (list, tuple, set)) else [raw_filter]
    allowed_normalized = {str(item).strip().lower() for item in allowed if str(item).strip()}
    return str(value or "").strip().lower() in allowed_normalized


def _match_text(value: Any, query: str | None) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return True
    return text in str(value or "").lower()


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _coerce_model(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if isinstance(item, dict):
        return dict(item)
    return {"value": item}


def _first_camera_id(payload: dict[str, Any]) -> str | None:
    camera_id = payload.get("camera_id")
    if camera_id:
        return str(camera_id)
    camera_ids = payload.get("camera_ids") or payload.get("metadata", {}).get("camera_ids") or []
    if isinstance(camera_ids, (list, tuple)) and camera_ids:
        return str(camera_ids[0])
    return None


class AnalyticsRepository:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        case_repository: Any | None = None,
        audit_service: Any | None = None,
        identity_db: Any | None = None,
        incident_repository: Any | None = None,
        event_bus: Any | None = None,
        runtime_stream_manager: Any | None = None,
        stream_session_manager: Any | None = None,
        monitoring_metrics: Any | None = None,
        system_snapshot_provider: Any | None = None,
        identity_store: Any | None = None,
        global_registry: Any | None = None,
        runtime: Any | None = None,
    ) -> None:
        self._raw_config = config or load_analytics_config()
        self._config = dict(self._raw_config.get("analytics") or {})
        self._lock = threading.RLock()
        self._case_repository = case_repository or get_case_repository()
        self._audit_service = audit_service or get_audit_log_service()
        self._identity_db = identity_db or get_db()
        self._incident_repository = incident_repository or get_incident_repository()
        self._event_bus = event_bus or get_event_bus()
        self._runtime_stream_manager = runtime_stream_manager or get_runtime_stream_session_manager()
        self._stream_session_manager = stream_session_manager or get_stream_session_manager()
        self._monitoring_metrics = monitoring_metrics or get_metrics()
        self._system_snapshot_provider = system_snapshot_provider or get_system_snapshot
        self._identity_store = identity_store or get_identity_store()
        self._global_registry = global_registry or get_global_registry()
        self._runtime = runtime
        self._source_status: dict[str, str] = {}
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", True))

    @property
    def storage_backend(self) -> str:
        storage_cfg = dict(self._config.get("storage") or {})
        if _is_production():
            return str(storage_cfg.get("production_backend") or "postgres")
        return str(storage_cfg.get("dev_backend") or "jsonl")

    def get_source_statuses(self) -> dict[str, str]:
        with self._lock:
            return dict(self._source_status)

    def get_last_error(self) -> str | None:
        return self._last_error

    def probe_sources(self) -> dict[str, str]:
        statuses: dict[str, str] = {}
        sources_cfg = dict(self._config.get("sources") or {})
        case_health = self._case_repository.health()
        source_mappings = {
            "cases": case_health.get("status", "degraded"),
            "evidence": case_health.get("status", "degraded"),
            "streaming": "healthy",
            "model_metrics": "healthy" if (PROJECT_ROOT / "storage" / "evaluation_runs").exists() else "missing",
            "system_health": "healthy",
            "events": "healthy",
            "anomaly": "healthy",
            "identity": "healthy",
            "open_vocab": "healthy" if (PROJECT_ROOT / "storage" / "open_vocab").exists() else "missing",
            "audit": "healthy" if (PROJECT_ROOT / "storage" / "audit").exists() else "missing",
        }
        for source_name, enabled in sources_cfg.items():
            if not enabled:
                continue
            statuses[source_name] = source_mappings.get(source_name, "healthy")
            self._set_source_status(source_name, statuses[source_name])
        if not statuses:
            return {}
        return statuses

    def get_events(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        had_source = False

        try:
            had_source = True
            for record in self._identity_db.get_events(limit=int(filters.get("limit") or 5000)):
                normalized = self._normalize_db_event(record)
                if normalized is None or not self._match_event(normalized, start, end, filters):
                    continue
                seen_ids.add(str(normalized["event_id"]))
                items.append(normalized)
        except Exception as exc:
            self._set_source_status("events", "degraded")
            self._last_error = str(exc)

        try:
            had_source = True
            for record in self._incident_repository.list_events(
                {
                    "limit": int(filters.get("limit") or 5000),
                    "source_type": filters.get("source_type"),
                    "camera_id": filters.get("camera_id"),
                    "session_id": filters.get("session_id"),
                    "case_id": filters.get("case_id"),
                    "event_type": filters.get("event_type") or filters.get("type"),
                    "severity": filters.get("severity"),
                }
            ):
                normalized = self._normalize_incident_event(record)
                if normalized is None:
                    continue
                if str(normalized["event_id"]) in seen_ids:
                    continue
                if not self._match_event(normalized, start, end, filters):
                    continue
                seen_ids.add(str(normalized["event_id"]))
                items.append(normalized)
        except Exception as exc:
            self._set_source_status("events", "degraded")
            self._last_error = str(exc)

        try:
            had_source = True
            for record in self._event_bus.replay_recent(limit=int(filters.get("bus_limit") or 2000)):
                normalized = self._normalize_bus_event(record)
                if normalized is None:
                    continue
                if str(normalized["event_id"]) in seen_ids:
                    continue
                if not self._match_event(normalized, start, end, filters):
                    continue
                seen_ids.add(str(normalized["event_id"]))
                items.append(normalized)
        except Exception as exc:
            self._set_source_status("events", "degraded")
            self._last_error = str(exc)

        items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
        self._set_source_status("events", "healthy" if had_source else "missing")
        return items

    def get_cases(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        try:
            for case in self._case_repository.list_cases({}):
                payload = _coerce_model(case)
                created_at = _parse_datetime(payload.get("created_at"))
                if created_at is not None and not (start <= created_at <= end):
                    continue
                if not self._match_case(payload, filters):
                    continue
                items.append(payload)
            self._set_source_status("cases", self._case_repository.health().get("status", "healthy"))
        except Exception as exc:
            self._set_source_status("cases", "degraded")
            self._last_error = str(exc)
        items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return items

    def get_evidence(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        try:
            for case in self._case_repository.list_cases({}):
                case_payload = _coerce_model(case)
                if filters.get("case_id") and str(filters["case_id"]) != str(case_payload.get("case_id")):
                    continue
                for evidence in self._case_repository.list_evidence(case_payload["case_id"]):
                    payload = _coerce_model(evidence)
                    evidence_at = _parse_datetime(payload.get("timestamp") or payload.get("created_at"))
                    if evidence_at is not None and not (start <= evidence_at <= end):
                        continue
                    if filters.get("camera_id") and str(filters["camera_id"]) != str(payload.get("camera_id") or ""):
                        continue
                    items.append(payload)
            self._set_source_status("evidence", self._case_repository.health().get("status", "healthy"))
        except Exception as exc:
            self._set_source_status("evidence", "degraded")
            self._last_error = str(exc)
        items.sort(key=lambda item: item.get("timestamp") or item.get("created_at") or "", reverse=True)
        return items

    def get_case_notes(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        try:
            for case in self._case_repository.list_cases({}):
                case_payload = _coerce_model(case)
                if filters.get("case_id") and str(filters["case_id"]) != str(case_payload.get("case_id")):
                    continue
                for note in self._case_repository.list_notes(case_payload["case_id"]):
                    payload = _coerce_model(note)
                    created_at = _parse_datetime(payload.get("created_at"))
                    if created_at is not None and not (start <= created_at <= end):
                        continue
                    items.append(payload)
        except Exception:
            pass
        return items

    def get_case_audit_logs(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        try:
            for case in self._case_repository.list_cases({}):
                case_payload = _coerce_model(case)
                if filters.get("case_id") and str(filters["case_id"]) != str(case_payload.get("case_id")):
                    continue
                for audit in self._case_repository.list_audit_logs(case_payload["case_id"]):
                    payload = _coerce_model(audit)
                    created_at = _parse_datetime(payload.get("timestamp"))
                    if created_at is not None and not (start <= created_at <= end):
                        continue
                    items.append(payload)
        except Exception:
            pass
        return items

    def get_stream_health(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del time_range
        filters = filters or {}
        items: list[dict[str, Any]] = []
        try:
            for entry in self._stream_session_manager.list_stream_states():
                camera_id = str(entry.get("camera_id") or "")
                if filters.get("camera_id") and str(filters["camera_id"]) != camera_id:
                    continue
                payload = {
                    "camera_id": camera_id,
                    "state": entry.get("state", "unknown"),
                    "stream_id": entry.get("stream_id"),
                    "updated_at": entry.get("updated_at"),
                    "health": dict(entry.get("health") or {}),
                    "stats": dict(entry.get("stats") or {}),
                }
                items.append(payload)
            self._set_source_status("streaming", "healthy")
        except Exception as exc:
            self._set_source_status("streaming", "degraded")
            self._last_error = str(exc)
        return items

    def get_model_metrics(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        events = self.get_events(time_range, filters)
        metrics_snapshot = self._monitoring_metrics.snapshot()
        items = [
            self._build_detection_summary("phone", "phone_detector", "Phone Detector", events),
            self._build_detection_summary("weapon", "weapon_detector", "Weapon Detector", events),
            self._build_anomaly_summary(metrics_snapshot),
            self._build_open_vocab_summary(metrics_snapshot),
            self._build_segmentation_summary(metrics_snapshot),
        ]
        self._set_source_status("model_metrics", "healthy")
        return items

    def get_audit_activity(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        try:
            items = self._audit_service.list_logs(
                user_id=filters.get("user_id"),
                action=filters.get("action"),
                resource_type=filters.get("resource_type"),
                start_time=start.timestamp(),
                end_time=end.timestamp(),
                limit=int(filters.get("limit") or 5000),
            )
            self._set_source_status("audit", "healthy")
            return list(items)
        except Exception as exc:
            self._set_source_status("audit", "degraded")
            self._last_error = str(exc)
            return []

    def get_identity_profiles(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        try:
            items = [
                _coerce_model(profile)
                for profile in self._identity_store.list_identities(
                    status=filters.get("status"),
                    tag=filters.get("tag"),
                    limit=int(filters.get("limit") or 500),
                )
            ]
            self._set_source_status("identity", "healthy")
            return items
        except Exception as exc:
            self._set_source_status("identity", "degraded")
            self._last_error = str(exc)
            return []

    def get_identity_matches(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        items: list[dict[str, Any]] = []
        try:
            for match in self._identity_store.list_matches(
                identity_id=filters.get("identity_id"),
                limit=int(filters.get("limit") or 500),
            ):
                payload = _coerce_model(match)
                matched_at = _parse_datetime(payload.get("matched_at"))
                if matched_at is not None and not (start <= matched_at <= end):
                    continue
                if filters.get("camera_id") and str(filters["camera_id"]) != str(payload.get("camera_id") or ""):
                    continue
                items.append(payload)
            self._set_source_status("identity", "healthy")
        except Exception as exc:
            self._set_source_status("identity", "degraded")
            self._last_error = str(exc)
        items.sort(key=lambda item: float(item.get("matched_at") or 0.0), reverse=True)
        return items

    def get_global_identity_records(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        try:
            items = self._global_registry.list_records(
                status=filters.get("status"),
                limit=int(filters.get("limit") or 500),
            )
            self._set_source_status("identity", "healthy")
            return list(items)
        except Exception as exc:
            self._set_source_status("identity", "degraded")
            self._last_error = str(exc)
            return []

    def get_open_vocab_results(self, time_range: AnalyticsTimeRange | dict[str, Any], filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        start, end = _range_bounds(time_range)
        try:
            runtime = self._runtime or self._get_runtime()
            payload = runtime.get_open_vocab_results(
                camera_id=filters.get("camera_id"),
                incident_id=filters.get("incident_id"),
                limit=int(filters.get("limit") or 1000),
            )
            items = []
            for item in payload.get("items", []):
                created_at = _parse_datetime(item.get("created_at"))
                if created_at is not None and not (start <= created_at <= end):
                    continue
                items.append(dict(item))
            self._set_source_status("open_vocab", "healthy" if payload.get("status") != "unavailable" else "missing")
            items.sort(key=lambda item: float(item.get("created_at") or 0.0), reverse=True)
            return items
        except Exception as exc:
            self._set_source_status("open_vocab", "degraded")
            self._last_error = str(exc)
            return []

    def get_system_metrics(self) -> dict[str, Any]:
        try:
            metrics = self._monitoring_metrics.snapshot()
            system = self._system_snapshot_provider() if callable(self._system_snapshot_provider) else {}
            event_bus_health = self._event_bus.health() if hasattr(self._event_bus, "health") else {}
            self._set_source_status("system_health", "healthy")
            return {
                "metrics": metrics,
                "system": system,
                "event_bus": event_bus_health,
                "streaming": self._runtime_stream_manager.health_summary(),
            }
        except Exception as exc:
            self._set_source_status("system_health", "degraded")
            self._last_error = str(exc)
            return {"metrics": {}, "system": {}, "event_bus": {}, "streaming": {}}

    def _build_detection_summary(
        self,
        keyword: str,
        model_key: str,
        display_name: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        report = self._load_latest_detection_report(keyword)
        matching_events = [item for item in events if keyword in str(item.get("event_type", "")).lower()]
        confidences = [float(item.get("confidence") or 0.0) for item in matching_events if item.get("confidence") is not None]
        latency = (((report or {}).get("metrics") or {}).get("inference_latency") or {})
        return {
            "model_key": model_key,
            "display_name": display_name,
            "status": "healthy" if report else "snapshot_only",
            "avg_latency_ms": latency.get("mean_ms"),
            "p95_latency_ms": latency.get("p95_ms"),
            "avg_confidence": _safe_average(confidences) if confidences else None,
            "event_count": len(matching_events),
            "benchmark_metrics": (report or {}).get("metrics") or {},
            "source": report.get("source", "runtime") if report else "runtime",
        }

    def _build_anomaly_summary(self, metrics_snapshot: dict[str, Any]) -> dict[str, Any]:
        report = self._load_latest_anomaly_report()
        report_metrics = ((report or {}).get("metrics") or {}) if report else {}
        return {
            "model_key": "videomae_anomaly",
            "display_name": "VideoMAE Anomaly Detector",
            "status": "healthy" if report else "runtime_only",
            "avg_latency_ms": metrics_snapshot.get("anomaly_model_latency_ms"),
            "p95_latency_ms": report_metrics.get("p95_latency_ms"),
            "avg_confidence": metrics_snapshot.get("anomaly_score_last"),
            "event_count": int(metrics_snapshot.get("anomaly_events_generated_total") or 0),
            "benchmark_metrics": report_metrics,
            "source": report.get("source", "runtime") if report else "runtime",
        }

    def _build_open_vocab_summary(self, metrics_snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "model_key": "open_vocab",
            "display_name": "Open-Vocabulary Scanner",
            "status": "healthy",
            "avg_latency_ms": metrics_snapshot.get("open_vocab_scan_latency_ms_avg"),
            "p95_latency_ms": None,
            "avg_confidence": None,
            "event_count": int(metrics_snapshot.get("open_vocab_threats_found") or 0),
            "benchmark_metrics": {
                "scans_requested": metrics_snapshot.get("open_vocab_scans_requested", 0),
                "scans_completed": metrics_snapshot.get("open_vocab_scans_completed", 0),
                "scan_failures": metrics_snapshot.get("open_vocab_scans_failed", 0),
            },
            "source": "runtime",
        }

    def _build_segmentation_summary(self, metrics_snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "model_key": "sam2_segmentation",
            "display_name": "SAM2 Segmentation",
            "status": "healthy" if int(metrics_snapshot.get("segmentation_requests_total") or 0) > 0 else "idle",
            "avg_latency_ms": metrics_snapshot.get("segmentation_latency_ms"),
            "p95_latency_ms": None,
            "avg_confidence": None,
            "event_count": int(metrics_snapshot.get("segmentation_masks_generated_total") or 0),
            "benchmark_metrics": {
                "requests_total": metrics_snapshot.get("segmentation_requests_total", 0),
                "masks_generated_total": metrics_snapshot.get("segmentation_masks_generated_total", 0),
                "provider_unavailable_total": metrics_snapshot.get("segmentation_provider_unavailable_total", 0),
            },
            "source": "runtime",
        }

    def _load_latest_detection_report(self, keyword: str) -> dict[str, Any] | None:
        base_dir = PROJECT_ROOT / "storage" / "evaluation_runs"
        if not base_dir.exists():
            return None
        candidates = sorted(
            [path for path in base_dir.glob(f"run_*_detection_{keyword}_*") if path.is_dir()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            metrics_path = candidate / "metrics.json"
            if not metrics_path.exists():
                continue
            try:
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            task_results = payload.get("task_results") or []
            metrics = task_results[0].get("metrics") if task_results else {}
            return {
                "source": candidate.name,
                "metrics": metrics or {},
            }
        return None

    def _load_latest_anomaly_report(self) -> dict[str, Any] | None:
        base_dir = PROJECT_ROOT / "storage" / "evaluation_runs" / "anomaly"
        if not base_dir.exists():
            return None
        candidates = sorted(base_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            return {
                "source": candidate.name,
                "metrics": payload.get("metrics") or payload,
            }
        return None

    def _normalize_db_event(self, record: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(record, dict):
            return None
        metadata = dict(record.get("metadata") or {})
        camera_ids = list(metadata.get("camera_ids") or [])
        camera_id = metadata.get("camera_id") or (camera_ids[0] if camera_ids else None)
        severity = str(record.get("severity") or "low").lower()
        return {
            "event_id": str(record.get("event_id") or ""),
            "event_type": str(record.get("event_type") or "event").lower(),
            "timestamp": _dt_to_iso(_parse_datetime(record.get("timestamp"))) or _now_iso(),
            "severity": severity,
            "confidence": float(record.get("confidence") or 0.0),
            "risk_score": float(record.get("risk_score") or 0.0),
            "camera_id": str(camera_id) if camera_id else None,
            "camera_ids": [str(item) for item in camera_ids if item],
            "metadata": metadata,
            "source": "identity_db",
        }

    def _normalize_bus_event(self, record: Any) -> dict[str, Any] | None:
        payload = getattr(record, "payload", None)
        if payload is None and isinstance(record, dict):
            payload = record.get("payload") or record
        data = _coerce_model(payload)
        timestamp = (
            _dt_to_iso(_parse_datetime(data.get("timestamp") or data.get("created_at")))
            or _dt_to_iso(_parse_datetime(getattr(record, "timestamp", None)))
            or _now_iso()
        )
        camera_ids = data.get("camera_ids") or data.get("metadata", {}).get("camera_ids") or []
        camera_id = data.get("camera_id") or (camera_ids[0] if isinstance(camera_ids, list) and camera_ids else None) or getattr(record, "source", None)
        severity = str(
            data.get("severity")
            or data.get("priority_level")
            or data.get("highest_risk")
            or "medium"
        ).lower()
        event_type = str(data.get("event_type") or getattr(record, "event_type", "event")).lower()
        event_id = (
            data.get("event_id")
            or data.get("scan_id")
            or data.get("window_id")
            or getattr(record, "event_id", None)
        )
        confidence = data.get("confidence") or data.get("confidence_score") or data.get("score") or 0.0
        risk_score = data.get("risk_score") or data.get("severity_score") or data.get("score") or 0.0
        return {
            "event_id": str(event_id or ""),
            "event_type": event_type,
            "timestamp": timestamp,
            "severity": severity,
            "confidence": float(confidence or 0.0),
            "risk_score": float(risk_score or 0.0),
            "camera_id": str(camera_id) if camera_id else None,
            "camera_ids": [str(item) for item in camera_ids] if isinstance(camera_ids, list) else ([] if camera_id is None else [str(camera_id)]),
            "metadata": data.get("metadata") or {},
            "source": "event_bus",
        }

    def _normalize_incident_event(self, record: Any) -> dict[str, Any] | None:
        payload = _coerce_model(record)
        session_id = payload.get("session_id")
        source_type = str(payload.get("source_type") or "live_stream").lower()
        camera_id = payload.get("camera_id")
        if not camera_id and source_type == "uploaded_video" and session_id:
            camera_id = f"uploaded:{session_id}"
        return {
            "event_id": str(payload.get("event_id") or ""),
            "event_type": str(payload.get("event_type") or "event").lower(),
            "timestamp": _dt_to_iso(_parse_datetime(payload.get("timestamp"))) or _now_iso(),
            "severity": str(payload.get("severity") or "medium").lower(),
            "confidence": float((payload.get("metadata") or {}).get("confidence") or 0.0),
            "risk_score": float(payload.get("risk_score") or 0.0),
            "camera_id": str(camera_id) if camera_id else None,
            "camera_ids": [str(camera_id)] if camera_id else [],
            "metadata": payload.get("metadata") or {},
            "source": source_type,
            "source_type": source_type,
            "session_id": session_id,
            "case_id": payload.get("case_id"),
            "frame_index": payload.get("frame_index"),
            "time_offset_seconds": payload.get("time_offset_seconds"),
        }

    def _match_event(self, payload: dict[str, Any], start: datetime, end: datetime, filters: dict[str, Any]) -> bool:
        event_at = _parse_datetime(payload.get("timestamp"))
        if event_at is not None and not (start <= event_at <= end):
            return False
        if not _match_scalar_filter(payload.get("event_type"), filters.get("event_type") or filters.get("type")):
            return False
        if not _match_scalar_filter(payload.get("severity"), filters.get("severity")):
            return False
        if filters.get("camera_id") and str(filters["camera_id"]) not in {str(payload.get("camera_id") or "")} | {str(item) for item in payload.get("camera_ids", [])}:
            return False
        if filters.get("source_type") and str(filters["source_type"]).lower() != str(payload.get("source_type") or payload.get("source") or "").lower():
            return False
        if filters.get("session_id") and str(filters["session_id"]) != str(payload.get("session_id") or ""):
            return False
        if filters.get("case_id") and str(filters["case_id"]) != str(payload.get("case_id") or ""):
            return False
        if not _match_text(json.dumps(payload.get("metadata") or {}), filters.get("q")):
            return False
        return True

    def _match_case(self, payload: dict[str, Any], filters: dict[str, Any]) -> bool:
        if not _match_scalar_filter(payload.get("status"), filters.get("status")):
            return False
        if not _match_scalar_filter(payload.get("severity"), filters.get("severity")):
            return False
        if not _match_scalar_filter(payload.get("priority"), filters.get("priority")):
            return False
        if filters.get("camera_id") and str(filters["camera_id"]) not in {str(item) for item in payload.get("camera_ids", [])}:
            return False
        if filters.get("assigned_to") and str(filters["assigned_to"]) != str(payload.get("assigned_to") or ""):
            return False
        if filters.get("requires_review") is not None and bool(filters.get("requires_review")) != bool(payload.get("requires_review")):
            return False
        if filters.get("review_status") and str(filters["review_status"]) != str(payload.get("review_status") or ""):
            return False
        combined = " ".join(
            [
                str(payload.get("case_id") or ""),
                str(payload.get("title") or ""),
                str(payload.get("description") or ""),
            ]
        )
        if not _match_text(combined, filters.get("q")):
            return False
        return True

    def _get_runtime(self):
        if self._runtime is None:
            from inference.runtime import get_intelligence_runtime

            self._runtime = get_intelligence_runtime()
        return self._runtime

    def _set_source_status(self, source_name: str, status: str) -> None:
        with self._lock:
            self._source_status[source_name] = status
        if status == "missing":
            self._increment_metric("analytics_source_missing_total")

    @staticmethod
    def _increment_metric(name: str, count: int = 1) -> None:
        try:
            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics as core_metrics

            core_metrics.increment(name, count)
        except Exception:
            pass
