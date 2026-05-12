from __future__ import annotations
import logging
import os
import time
from pathlib import Path

from app.core.persistence import (
    get_store_backend,
    is_production_environment,
    latest_backup_manifest,
    managed_storage_summary,
    persistence_enabled,
    postgres_dsn,
    prohibit_jsonl_fallback,
    require_managed_artifact_storage,
    require_postgres,
    store_required_in_production,
)
from app.db.schema_bootstrap import connect_postgres, verify_required_tables

logger = logging.getLogger(__name__)


class RuntimeHealthService:
    """Aggregates subsystem health for readiness/liveness/health endpoints."""

    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def _check_database(self) -> dict:
        dsn = os.environ.get("POSTGRES_DSN", "")
        if not dsn:
            return {"status": "degraded", "detail": "POSTGRES_DSN not configured"}
        try:
            import psycopg2
            conn = psycopg2.connect(dsn, connect_timeout=3)
            conn.close()
            return {"status": "ok", "detail": None}
        except ImportError:
            return {"status": "degraded", "detail": "psycopg2 not installed"}
        except Exception as e:
            return {"status": "error", "detail": str(e)[:120]}

    def _check_redis(self) -> dict:
        url = os.environ.get("REDIS_URL", "")
        if not url:
            return {"status": "degraded", "detail": "REDIS_URL not configured"}
        try:
            import redis
            r = redis.from_url(url, socket_connect_timeout=3)
            r.ping()
            return {"status": "ok", "detail": None}
        except ImportError:
            return {"status": "degraded", "detail": "redis package not installed"}
        except Exception as e:
            return {"status": "error", "detail": str(e)[:120]}

    def _check_gpu(self) -> dict:
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                return {"status": "ok", "detail": f"cuda available: {device_name}"}
            return {"status": "degraded", "detail": "cuda not available — CPU mode"}
        except ImportError:
            return {"status": "degraded", "detail": "torch not installed"}

    def _check_open_vocab(self) -> dict:
        required = bool(self._config.get("services", {}).get("open_vocab", {}).get("required", False))
        try:
            from inference.runtime import get_intelligence_runtime

            status = get_intelligence_runtime().get_open_vocab_status()
        except Exception as exc:
            status = {
                "model_loaded": False,
                "auto_load_on_camera_start": False,
                "last_auto_load_status": "failed",
                "last_auto_load_error": str(exc),
            }

        model_loaded = bool(status.get("model_loaded") or status.get("adapter", {}).get("available"))
        last_status = status.get("last_auto_load_status", "disabled")
        last_error = status.get("last_auto_load_error") or status.get("reason") or status.get("error")
        if model_loaded:
            health_status = "ok"
            detail = None
        elif required:
            health_status = "error"
            detail = last_error or "open-vocab required but model not loaded"
        elif last_status in {"failed", "timeout"}:
            health_status = "degraded"
            detail = last_error or f"last auto-load status: {last_status}"
        elif last_status == "disabled":
            health_status = "degraded"
            detail = "auto-load disabled"
        else:
            health_status = "unavailable"
            detail = last_error or "open-vocab model not loaded"
        return {
            "status": health_status,
            "detail": detail,
            "model_loaded": model_loaded,
            "auto_load_on_camera_start": bool(status.get("auto_load_on_camera_start", False)),
            "last_auto_load_status": last_status,
            "last_auto_load_error": last_error,
        }

    def _check_segmentation(self) -> dict:
        try:
            from inference.segmentation import get_segmentation_service

            health = get_segmentation_service().get_health()
        except Exception as exc:
            return {
                "status": "failed",
                "detail": str(exc)[:120],
                "enabled": True,
                "provider": "unknown",
                "loaded": False,
            }
        detail = health.get("last_error")
        return {
            "status": health.get("status", "degraded"),
            "detail": detail,
            "enabled": bool(health.get("enabled", False)),
            "provider": health.get("provider"),
            "loaded": bool(health.get("loaded", False)),
            "device": health.get("device"),
        }

    def _check_storage(self) -> dict:
        paths = ["storage", "storage/open_vocab", "models"]
        for p in paths:
            path = Path(p)
            path.mkdir(parents=True, exist_ok=True)
            if not os.access(str(path), os.W_OK):
                return {"status": "error", "detail": f"storage path not writable: {p}"}
        return {"status": "ok", "detail": None}

    def _check_model_registry(self) -> dict:
        try:
            from ml.runtime.model_registry import ModelRegistry  # noqa: F401
            return {"status": "ok", "detail": None}
        except Exception as e:
            return {"status": "degraded", "detail": str(e)[:120]}

    def _check_model_governance(self) -> dict:
        try:
            from app.services.model_governance_service import evaluate_runtime_model_governance

            profile = "production" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "development"
            report = evaluate_runtime_model_governance(profile=profile)
            st = str(report.get("status") or "unknown")
            mapped = "error" if st == "failed" else ("degraded" if st == "degraded" else "ok")
            return {
                "status": mapped,
                "governance_status": st,
                "active_models": report.get("active_models") or [],
                "missing_registry_entries": report.get("missing_registry_entries") or [],
                "missing_metrics": report.get("missing_metrics") or [],
                "production_blockers": report.get("production_blockers") or [],
            }
        except Exception as exc:
            return {"status": "degraded", "detail": str(exc)[:160], "production_blockers": [str(exc)]}

    def _check_event_bus(self) -> dict:
        try:
            from core.event_bus.distributed_event_bus import DistributedEventBus  # noqa: F401
            return {"status": "ok", "detail": None}
        except Exception as e:
            return {"status": "degraded", "detail": str(e)[:120]}

    def _check_security(self) -> dict:
        secret = os.environ.get("AEGIS_JWT_SECRET", "")
        if not secret or secret == "change-this-in-production-use-a-long-random-string":
            env = os.environ.get("APP_ENV", "dev")
            if env == "production":
                return {"status": "error", "detail": "JWT secret is default/empty in production"}
            return {"status": "degraded", "detail": "JWT secret not set (dev mode)"}
        return {"status": "ok", "detail": None}

    def _check_identity(self) -> dict:
        try:
            from app.services.identity_service import get_identity_service

            health = get_identity_service().get_health()
        except Exception as exc:
            return {
                "status": "failed",
                "detail": str(exc)[:120],
                "enabled": True,
                "face_provider": "unknown",
                "face_loaded": False,
                "reid_provider": "unknown",
                "reid_loaded": False,
                "liveness_enabled": False,
            }
        detail = health.get("last_error")
        status_map = {
            "healthy": "ok",
            "degraded": "degraded",
            "disabled": "disabled",
            "failed": "error",
        }
        agg = status_map.get(health.get("status", "degraded"), "degraded")
        if health.get("liveness_enabled") and health.get("liveness_status") == "failed":
            agg = "error"
        cal = health.get("calibration") or {}
        inner_status = "healthy"
        if agg == "error":
            inner_status = "failed"
        elif agg == "degraded":
            inner_status = "degraded"
        return {
            "status": agg,
            "detail": detail,
            "enabled": bool(health.get("enabled", True)),
            "face_provider": health.get("face_provider"),
            "face_loaded": bool(health.get("face_loaded", False)),
            "reid_provider": health.get("reid_provider"),
            "reid_loaded": bool(health.get("reid_loaded", False)),
            "liveness_enabled": bool(health.get("liveness_enabled", False)),
            "liveness_provider": str(health.get("liveness_provider") or "none"),
            "calibration": {
                "face_calibrated": bool(cal.get("face_calibrated")),
                "reid_benchmarked": bool(cal.get("reid_benchmarked")),
            },
            "durable_registry": bool(health.get("durable_registry", False)),
            "identity": {
                "face_loaded": bool(health.get("face_loaded", False)),
                "reid_loaded": bool(health.get("reid_loaded", False)),
                "liveness_enabled": bool(health.get("liveness_enabled", False)),
                "liveness_provider": str(health.get("liveness_provider") or "none"),
                "calibration": {
                    "face_calibrated": bool(cal.get("face_calibrated")),
                    "reid_benchmarked": bool(cal.get("reid_benchmarked")),
                },
                "durable_registry": bool(health.get("durable_registry", False)),
                "status": inner_status,
            },
        }

    def _check_case_management(self) -> dict:
        try:
            from app.services.case_service import get_case_service

            health = get_case_service().health()
        except Exception as exc:
            return {
                "enabled": True,
                "storage": "unknown",
                "status": "failed" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "degraded",
                "case_count": 0,
                "open_case_count": 0,
                "last_error": str(exc)[:120],
            }
        return {
            "enabled": bool(health.get("enabled", False)),
            "storage": health.get("storage", "unknown"),
            "status": health.get("status", "disabled"),
            "case_count": int(health.get("case_count", 0)),
            "open_case_count": int(health.get("open_case_count", 0)),
            "last_error": health.get("last_error"),
        }

    def _check_llm(self) -> dict:
        try:
            from app.services.llm_service import get_llm_service

            health = get_llm_service().health()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "error" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "degraded",
                "detail": str(exc)[:120],
                "provider": "unknown",
                "active_provider": "unknown",
                "openai_key_present": False,
            }
        return {
            "enabled": bool(health.get("enabled", False)),
            "status": health.get("status", "disabled"),
            "detail": health.get("detail"),
            "provider": health.get("provider", "unknown"),
            "active_provider": health.get("active_provider", "unknown"),
            "openai_key_present": bool(health.get("openai_key_present", False)),
            "using_fallback": bool(health.get("using_fallback", False)),
        }

    def _check_osint_enrichment(self) -> dict:
        try:
            from app.services.osint_service import get_osint_service

            health = get_osint_service().health()
        except Exception as exc:
            return {
                "enabled": True,
                "mode": "analyst_provided_only",
                "storage": "unknown",
                "status": "failed" if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} else "degraded",
                "last_error": str(exc)[:120],
            }
        return {
            "enabled": bool(health.get("enabled", False)),
            "mode": str(health.get("mode") or "analyst_provided_only"),
            "storage": health.get("storage", "unknown"),
            "status": health.get("status", "disabled"),
            "last_error": health.get("last_error"),
        }

    def _check_streaming(self) -> dict:
        try:
            from app.services.rtsp_ingest_service import load_streaming_runtime_config
            from app.services.hls_service import get_hls_service
            from app.services.webrtc_service import AIORTC_AVAILABLE, AIORTC_IMPORT_ERROR
            from inference.stream.stream_session_manager import get_runtime_stream_session_manager

            cfg = load_streaming_runtime_config().get("streaming", {})
            summary = get_runtime_stream_session_manager().health_summary().get("streaming", {})
            enabled = bool(cfg.get("enabled", True))
            hls_enabled = bool(cfg.get("hls", {}).get("enabled", False))
            webrtc_enabled = bool(cfg.get("webrtc", {}).get("enabled", False))
            ffmpeg_available = bool(get_hls_service().ffmpeg_available)
            production_mode = (os.getenv("APP_ENV") or "").lower() in {"prod", "production"}
            missing: list[str] = []
            if enabled and hls_enabled and not ffmpeg_available:
                missing.append("ffmpeg")
            if enabled and webrtc_enabled and not AIORTC_AVAILABLE:
                missing.append("aiortc")
            if not enabled:
                status = "disabled"
            elif missing and production_mode:
                status = "error"
            elif missing:
                status = "degraded"
            else:
                status = summary.get("status", "healthy")
            return {
                **summary,
                "enabled": enabled,
                "status": status,
                "hls_enabled": hls_enabled,
                "webrtc_enabled": webrtc_enabled,
                "ffmpeg_available": ffmpeg_available,
                "aiortc_available": AIORTC_AVAILABLE,
                "last_error": AIORTC_IMPORT_ERROR if (webrtc_enabled and not AIORTC_AVAILABLE) else summary.get("last_error"),
                "missing_dependencies": missing,
            }
        except Exception as exc:
            return {
                "enabled": False,
                "status": "degraded",
                "last_error": str(exc)[:120],
                "missing_dependencies": [],
            }

    def _check_gis(self) -> dict:
        try:
            from app.repositories.gis_repository import get_gis_repository
            from app.services.gis_service import evaluate_gis_readiness

            report = evaluate_gis_readiness()
            repo = get_gis_repository()
            st = str(report.get("status") or "unknown")
            mapped = "error" if st == "failed" else ("degraded" if st == "degraded" else "ok")
            return {
                "enabled": bool(report.get("enabled", True)),
                "status": "healthy" if mapped == "ok" else ("degraded" if mapped == "degraded" else "failed"),
                "provider": str(report.get("provider") or "local_mock"),
                "camera_profiles": int(repo.count_camera_profiles()),
                "geofences": int(repo.count_geofences()),
                "last_error": report.get("last_error"),
            }
        except Exception as exc:
            return {
                "enabled": True,
                "status": "degraded",
                "provider": "unknown",
                "camera_profiles": 0,
                "geofences": 0,
                "last_error": str(exc)[:160],
            }

    def _check_analytics(self) -> dict:
        production_mode = (os.getenv("APP_ENV") or "").lower() in {"prod", "production"}
        try:
            from app.services.analytics_service import get_analytics_service

            health = get_analytics_service().get_health().model_dump(mode="json")
        except Exception as exc:
            return {
                "enabled": True,
                "storage": "unknown",
                "status": "failed" if production_mode else "degraded",
                "sources": {},
                "last_error": str(exc)[:120],
            }
        return {
            "enabled": bool(health.get("enabled", False)),
            "storage": health.get("storage", "unknown"),
            "status": health.get("status", "disabled"),
            "sources": dict(health.get("sources") or {}),
            "last_error": health.get("last_error"),
        }

    def _check_uploaded_video(self) -> dict:
        try:
            from app.services.uploaded_video_service import get_uploaded_video_service

            health = get_uploaded_video_service().health()
        except Exception as exc:
            return {
                "enabled": True,
                "status": "failed" if self._production_mode() else "degraded",
                "active_sessions": 0,
                "completed_sessions": 0,
                "failed_sessions": 0,
                "storage": "filesystem",
                "last_error": str(exc)[:160],
            }
        return {
            "enabled": bool(health.get("enabled", False)),
            "status": str(health.get("status") or "disabled"),
            "active_sessions": int(health.get("active_sessions", 0)),
            "completed_sessions": int(health.get("completed_sessions", 0)),
            "failed_sessions": int(health.get("failed_sessions", 0)),
            "storage": str(health.get("storage") or "filesystem"),
            "last_error": health.get("last_error"),
            "uploaded_video": {
                "replay_enabled": bool(health.get("replay_enabled", False)),
                "ffmpeg_available": bool(health.get("ffmpeg_available", False)),
                "clip_generation_status": str(health.get("clip_generation_status") or "unknown"),
            },
        }

    @staticmethod
    def _production_mode() -> bool:
        return is_production_environment()

    @staticmethod
    def _store_payload(*, store: str, backend: str, status: str, last_error: str | None = None, **extra) -> dict:
        payload = {
            "store": store,
            "backend": backend,
            "status": status,
            "last_error": last_error,
        }
        payload.update(extra)
        return payload

    def _check_event_persistence(self) -> dict:
        configured_backend = get_store_backend("events", default_dev="jsonl", default_prod="postgres")
        try:
            from inference.identity_db import get_db

            db = get_db()
            if getattr(db, "db_healthy", False):
                return self._store_payload(store="events", backend="postgres", status="healthy")
            if self._production_mode():
                return self._store_payload(
                    store="events",
                    backend="postgres",
                    status="failed",
                    last_error="Event persistence PostgreSQL backend is unavailable",
                    configured_backend=configured_backend,
                )
            return self._store_payload(
                store="events",
                backend="memory",
                status="healthy",
                last_error="development fallback uses in-memory event persistence",
                configured_backend=configured_backend,
            )
        except Exception as exc:
            return self._store_payload(
                store="events",
                backend=configured_backend,
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )

    def _check_evidence_file_store(self) -> dict:
        try:
            from app.services.evidence_integrity import get_evidence_runtime_settings, get_evidence_storage_root

            settings = get_evidence_runtime_settings()
            storage_cfg = dict(settings.get("storage") or {})
            backend = get_store_backend("evidence_files", default_dev="filesystem", default_prod="managed_filesystem_or_s3")
            local_root = get_evidence_storage_root({"evidence": settings})
            writable = os.access(str(local_root), os.W_OK)
            managed_backend = backend.lower()
            managed_ready = (
                "managed" in managed_backend
                or "s3" in managed_backend
                or "artifact" in managed_backend
                or managed_backend in {"filesystem_or_s3", "s3_or_filesystem"}
            )
            if self._production_mode() and require_managed_artifact_storage() and not managed_ready:
                status = "failed"
                last_error = f"Artifact storage backend '{backend}' is not approved for production"
            elif not writable and (not self._production_mode() or backend in {"filesystem", "local", "managed_filesystem_or_s3"}):
                status = "failed" if self._production_mode() else "degraded"
                last_error = f"Evidence storage path is not writable: {local_root}"
            else:
                status = "healthy"
                last_error = None
            return self._store_payload(
                store="evidence_files",
                backend=backend,
                status=status,
                last_error=last_error,
                path=str(local_root),
                configured_backend=str(storage_cfg.get("production_backend") or storage_cfg.get("dev_backend") or backend),
            )
        except Exception as exc:
            return self._store_payload(
                store="evidence_files",
                backend=get_store_backend("evidence_files", default_dev="filesystem", default_prod="managed_filesystem_or_s3"),
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )

    def _check_model_registry_store(self) -> dict:
        try:
            from app.repositories.model_registry_repository import (
                FileModelRegistryRepository,
                get_model_registry_repository,
                get_model_registry_settings,
            )

            settings = get_model_registry_settings()
            repository = get_model_registry_repository()
            health = repository.health_check().to_dict()
            path = None
            if isinstance(repository, FileModelRegistryRepository):
                path = str(repository.file_path)
            return self._store_payload(
                store="model_registry",
                backend=str(settings.get("backend") or repository.storage_backend),
                status=str(health.get("status") or "degraded"),
                last_error=health.get("last_error"),
                path=path,
                allow_writes=bool(health.get("allow_writes", False)),
                prohibit_dual_writes=bool(settings.get("prohibit_dual_writes", True)),
            )
        except Exception as exc:
            return self._store_payload(
                store="model_registry",
                backend=get_store_backend("model_registry", default_dev="json", default_prod="postgres"),
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )

    def _check_persistence(self) -> dict:
        enabled = persistence_enabled()
        if not enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "stores": {},
                "failures": [],
                "warnings": [],
                "required_tables": {},
                "last_backup_at": None,
                "retention_mode": "disabled",
            }

        stores: dict[str, dict] = {}
        failures: list[str] = []
        warnings: list[str] = []

        case_health = self._check_case_management()
        case_store = self._store_payload(
            store="cases",
            backend=str(case_health.get("storage") or "unknown"),
            status=str(case_health.get("status") or "degraded"),
            last_error=case_health.get("last_error"),
        )
        stores["cases"] = case_store
        stores["evidence_metadata"] = self._store_payload(
            store="evidence_metadata",
            backend=case_store["backend"],
            status=case_store["status"],
            last_error=case_store.get("last_error"),
        )
        stores["evidence_files"] = self._check_evidence_file_store()
        stores["events"] = self._check_event_persistence()

        try:
            from app.services.identity_service import get_identity_service

            identity_persistence = dict((get_identity_service().get_health().get("persistence") or {}))
        except Exception as exc:
            identity_persistence = self._store_payload(
                store="identity_registry",
                backend="unknown",
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )
        stores["identity_registry"] = {
            "store": "identity_registry",
            "backend": str(identity_persistence.get("backend") or "unknown"),
            "status": str(identity_persistence.get("status") or "degraded"),
            "last_error": identity_persistence.get("last_error"),
        }

        try:
            from app.services.audit_log_service import get_audit_log_service

            audit_health = dict(get_audit_log_service().health())
        except Exception as exc:
            audit_health = self._store_payload(
                store="audit_logs",
                backend="unknown",
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )
        stores["audit_logs"] = {
            "store": "audit_logs",
            "backend": str(audit_health.get("backend") or audit_health.get("storage") or "unknown"),
            "status": str(audit_health.get("status") or "degraded"),
            "last_error": audit_health.get("last_error"),
        }

        osint_health = self._check_osint_enrichment()
        stores["osint"] = self._store_payload(
            store="osint",
            backend=str(osint_health.get("storage") or "unknown"),
            status=str(osint_health.get("status") or "degraded"),
            last_error=osint_health.get("last_error"),
        )

        try:
            from inference.open_vocab.result_store import OpenVocabResultStore

            open_vocab_health = dict(OpenVocabResultStore().health_check())
        except Exception as exc:
            open_vocab_health = self._store_payload(
                store="open_vocab_results",
                backend="unknown",
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )
        stores["open_vocab_results"] = {
            "store": "open_vocab_results",
            "backend": str(open_vocab_health.get("backend") or "unknown"),
            "status": str(open_vocab_health.get("status") or "degraded"),
            "last_error": open_vocab_health.get("last_error"),
        }

        try:
            from app.services.replay_clip_service import get_replay_clip_service

            replay_health = dict(get_replay_clip_service().health_check())
        except Exception as exc:
            replay_health = self._store_payload(
                store="stream_replay_metadata",
                backend="unknown",
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
            )
        stores["stream_replay_metadata"] = {
            "store": "stream_replay_metadata",
            "backend": str(replay_health.get("backend") or "unknown"),
            "status": str(replay_health.get("status") or "degraded"),
            "last_error": replay_health.get("last_error"),
        }

        try:
            from app.services.evidence_retention_service import get_evidence_retention_service

            retention_health = dict(get_evidence_retention_service().health_check())
        except Exception as exc:
            retention_health = self._store_payload(
                store="retention_actions",
                backend="unknown",
                status="failed" if self._production_mode() else "degraded",
                last_error=str(exc)[:160],
                retention_mode="unknown",
            )
        stores["retention_actions"] = {
            "store": "retention_actions",
            "backend": str(retention_health.get("backend") or "unknown"),
            "status": str(retention_health.get("status") or "degraded"),
            "last_error": retention_health.get("last_error"),
        }

        analytics_health = self._check_analytics()
        stores["analytics"] = self._store_payload(
            store="analytics",
            backend=str(analytics_health.get("storage") or "unknown"),
            status=str(analytics_health.get("status") or "degraded"),
            last_error=analytics_health.get("last_error"),
        )
        stores["model_registry"] = self._check_model_registry_store()

        required_tables: dict[str, bool] = {}
        if self._production_mode() and require_postgres():
            dsn = postgres_dsn()
            if not dsn:
                failures.append("POSTGRES_DSN missing while production persistence requires PostgreSQL")
            else:
                try:
                    with connect_postgres(dsn) as connection:
                        required_tables = verify_required_tables(connection)
                    missing_tables = sorted(name for name, present in required_tables.items() if not present)
                    if missing_tables:
                        failures.append(f"required tables missing: {', '.join(missing_tables)}")
                except Exception as exc:
                    failures.append(f"postgres readiness check failed: {str(exc)[:160]}")

        for store_name, payload in stores.items():
            store_status = str(payload.get("status") or "degraded")
            backend = str(payload.get("backend") or "unknown").lower()
            if self._production_mode() and store_required_in_production(store_name):
                if store_status in {"failed", "error"}:
                    failures.append(f"{store_name} store is {store_status}")
                if prohibit_jsonl_fallback() and backend == "jsonl":
                    failures.append(f"{store_name} is using prohibited JSONL fallback")
            elif store_status in {"failed", "error", "degraded"}:
                warnings.append(f"{store_name} store is {store_status}")

        if self._production_mode():
            evidence_files = stores.get("evidence_files") or {}
            if require_managed_artifact_storage() and str(evidence_files.get("status")) != "healthy":
                failures.append(evidence_files.get("last_error") or "artifact storage is unavailable")

        last_backup = latest_backup_manifest() or {}
        if failures:
            status = "failed"
        elif warnings:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "enabled": True,
            "status": status,
            "stores": stores,
            "failures": failures,
            "warnings": warnings,
            "required_tables": required_tables,
            "last_backup_at": last_backup.get("created_at"),
            "retention_mode": retention_health.get("retention_mode") if "retention_health" in locals() else "unknown",
            "production_requirements": {
                "require_postgres": require_postgres(),
                "require_managed_artifact_storage": require_managed_artifact_storage(),
                "prohibit_jsonl_fallback_for_required_stores": prohibit_jsonl_fallback(),
                "managed_storage": managed_storage_summary(),
            },
        }

    def get_health(self, include_sensitive: bool = False) -> dict:
        """Return aggregated health status for all subsystems."""
        case_management = self._check_case_management()
        llm = self._check_llm()
        osint_enrichment = self._check_osint_enrichment()
        streaming = self._check_streaming()
        analytics = self._check_analytics()
        uploaded_video = self._check_uploaded_video()
        persistence = self._check_persistence()
        gis = self._check_gis()
        checks = {
            "database": self._check_database(),
            "redis": self._check_redis(),
            "gpu": self._check_gpu(),
            "identity": self._check_identity(),
            "open_vocab": self._check_open_vocab(),
            "segmentation": self._check_segmentation(),
            "storage": self._check_storage(),
            "model_registry": self._check_model_registry(),
            "model_governance": self._check_model_governance(),
            "event_bus": self._check_event_bus(),
            "security": self._check_security(),
            "case_management": case_management,
            "llm": llm,
            "osint_enrichment": osint_enrichment,
            "streaming": streaming,
            "analytics": analytics,
            "uploaded_video": uploaded_video,
            "persistence": persistence,
            "gis": gis,
        }

        if not include_sensitive:
            for k in checks:
                if checks[k].get("detail") and "path" in str(checks[k]["detail"]).lower():
                    checks[k] = dict(checks[k])
                    checks[k]["detail"] = "[filtered]"
            if "persistence" in checks:
                filtered_persistence = dict(checks["persistence"])
                filtered_stores = {}
                for store_name, payload in dict(filtered_persistence.get("stores") or {}).items():
                    filtered_payload = dict(payload)
                    if filtered_payload.get("path"):
                        filtered_payload["path"] = "[filtered]"
                    if filtered_payload.get("last_error") and "path" in str(filtered_payload["last_error"]).lower():
                        filtered_payload["last_error"] = "[filtered]"
                    filtered_stores[store_name] = filtered_payload
                filtered_persistence["stores"] = filtered_stores
                checks["persistence"] = filtered_persistence

        statuses = [c["status"] for c in checks.values()]
        if "error" in statuses or "failed" in statuses:
            overall = "error"
        elif "degraded" in statuses or "unavailable" in statuses:
            overall = "degraded"
        else:
            overall = "ok"

        return {
            "status": overall,
            "generated_at": time.time(),
            "checks": checks,
            "case_management": case_management,
            "llm": llm,
            "osint_enrichment": osint_enrichment,
            "streaming": streaming,
            "analytics": analytics,
            "uploaded_video": uploaded_video,
            "persistence": persistence,
            "gis": gis,
        }

    def is_alive(self) -> bool:
        """Liveness check — always true if process is running."""
        return True

    def is_ready(self) -> dict:
        """Check only required dependencies based on deployment config."""
        deploy_config = self._config.get("runtime", {})
        require_postgres = deploy_config.get("require_postgres", False)
        require_redis = deploy_config.get("require_redis", False)
        require_gpu = deploy_config.get("require_gpu", False)
        require_open_vocab = bool(self._config.get("services", {}).get("open_vocab", {}).get("required", False))
        require_segmentation = bool(self._config.get("services", {}).get("segmentation", {}).get("required", False))
        require_identity = True

        failures = []
        identity_check = self._check_identity()
        if require_postgres:
            db = self._check_database()
            if db["status"] != "ok":
                failures.append(f"database: {db['detail']}")
        if require_redis:
            rd = self._check_redis()
            if rd["status"] != "ok":
                failures.append(f"redis: {rd['detail']}")
        if require_gpu:
            gpu = self._check_gpu()
            if gpu["status"] != "ok":
                failures.append(f"gpu: {gpu['detail']}")

        storage = self._check_storage()
        if storage["status"] == "error":
            failures.append(f"storage: {storage['detail']}")

        security = self._check_security()
        if security["status"] == "error":
            failures.append(f"security: {security['detail']}")

        if require_open_vocab:
            open_vocab = self._check_open_vocab()
            if open_vocab["status"] != "ok":
                failures.append(f"open_vocab: {open_vocab['detail']}")
        if require_segmentation:
            segmentation = self._check_segmentation()
            if segmentation["status"] != "healthy":
                failures.append(f"segmentation: {segmentation.get('detail') or segmentation['status']}")
        if require_identity:
            if identity_check["status"] in {"error", "failed"}:
                failures.append(f"identity: {identity_check.get('detail') or identity_check['status']}")
        try:
            from inference.identity.runtime_config import load_identity_config
            from inference.identity.liveness_adapter import LivenessAdapter

            icfg = load_identity_config()
            live = icfg.get("liveness") or {}
            if self._production_mode() and bool(icfg.get("enabled", True)) and bool(live.get("enabled")):
                lh = LivenessAdapter(config=icfg).get_health()
                if lh.get("status") == "failed":
                    failures.append("identity: liveness enabled but provider unavailable (liveness unavailable)")
            cal_cfg = icfg.get("calibration") or {}
            if self._production_mode() and bool(icfg.get("enabled", True)) and bool(cal_cfg.get("enabled", False)):
                snap = identity_check.get("calibration") or {}
                face_cfg = cal_cfg.get("face") or {}
                if bool(face_cfg.get("require_calibration_before_production", False)) and bool(
                    (icfg.get("face") or {}).get("enabled", False)
                ):
                    if not snap.get("face_calibrated"):
                        sev = str((icfg.get("production_readiness") or {}).get("calibration_missing_severity") or "fail")
                        if sev == "fail":
                            failures.append("identity: face calibration required before production")
                reid_cfg = cal_cfg.get("reid") or {}
                if bool(reid_cfg.get("require_benchmark_before_production", False)) and bool(
                    (icfg.get("reid") or {}).get("enabled", False)
                ):
                    if not snap.get("reid_benchmarked"):
                        sev = str((icfg.get("production_readiness") or {}).get("calibration_missing_severity") or "fail")
                        if sev == "fail":
                            failures.append("identity: ReID benchmark required before production")
        except Exception as exc:
            if self._production_mode():
                failures.append(f"identity readiness policy check failed: {str(exc)[:120]}")
        case_management = self._check_case_management()
        if case_management.get("enabled") and case_management.get("status") == "failed":
            failures.append(
                f"case_management: {case_management.get('last_error') or case_management.get('status')}"
            )
        llm = self._check_llm()
        if llm.get("enabled") and llm.get("status") == "error":
            failures.append(f"llm: {llm.get('detail') or llm.get('status')}")
        osint_enrichment = self._check_osint_enrichment()
        if osint_enrichment.get("enabled") and osint_enrichment.get("status") in {"failed", "error", "degraded"}:
            failures.append(
                f"osint_enrichment: {osint_enrichment.get('last_error') or osint_enrichment.get('status')}"
            )
        streaming = self._check_streaming()
        if streaming.get("enabled") and streaming.get("status") == "error":
            failures.append(
                f"streaming: {', '.join(streaming.get('missing_dependencies', [])) or streaming.get('last_error') or 'dependency failure'}"
            )
        analytics = self._check_analytics()
        if analytics.get("enabled") and analytics.get("status") in {"failed", "error"}:
            failures.append(
                f"analytics: {analytics.get('last_error') or analytics.get('status')}"
            )
        uploaded_video = self._check_uploaded_video()
        if uploaded_video.get("enabled") and uploaded_video.get("status") in {"failed", "error"}:
            failures.append(
                f"uploaded_video: {uploaded_video.get('last_error') or uploaded_video.get('status')}"
            )

        gis_check = self._check_gis()
        if self._production_mode() and gis_check.get("enabled") and gis_check.get("status") == "failed":
            failures.append(f"gis: {gis_check.get('last_error') or 'map provider not ready'}")

        persistence = self._check_persistence()
        if persistence.get("enabled", False) and persistence.get("status") == "failed":
            failures.extend(f"persistence: {item}" for item in persistence.get("failures") or [])

        return {
            "ready": len(failures) == 0,
            "failures": failures,
            "generated_at": time.time(),
            "persistence": persistence,
        }


# Module-level singleton for use in routes
_health_service: RuntimeHealthService | None = None


def get_runtime_health_service() -> RuntimeHealthService:
    """Return the process-wide RuntimeHealthService singleton."""
    global _health_service
    if _health_service is None:
        # Attempt to load deployment config
        config: dict = {}
        try:
            from inference.config_runtime import load_runtime_config
            config = load_runtime_config("deployment")
        except Exception:
            pass
        _health_service = RuntimeHealthService(config=config)
    return _health_service
