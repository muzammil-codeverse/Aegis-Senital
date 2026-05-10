from __future__ import annotations
import logging
import os
import time
from pathlib import Path

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
        return {
            "status": status_map.get(health.get("status", "degraded"), "degraded"),
            "detail": detail,
            "enabled": bool(health.get("enabled", True)),
            "face_provider": health.get("face_provider"),
            "face_loaded": bool(health.get("face_loaded", False)),
            "reid_provider": health.get("reid_provider"),
            "reid_loaded": bool(health.get("reid_loaded", False)),
            "liveness_enabled": bool(health.get("liveness_enabled", False)),
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

    def get_health(self, include_sensitive: bool = False) -> dict:
        """Return aggregated health status for all subsystems."""
        case_management = self._check_case_management()
        llm = self._check_llm()
        osint_enrichment = self._check_osint_enrichment()
        streaming = self._check_streaming()
        checks = {
            "database": self._check_database(),
            "redis": self._check_redis(),
            "gpu": self._check_gpu(),
            "identity": self._check_identity(),
            "open_vocab": self._check_open_vocab(),
            "segmentation": self._check_segmentation(),
            "storage": self._check_storage(),
            "model_registry": self._check_model_registry(),
            "event_bus": self._check_event_bus(),
            "security": self._check_security(),
            "case_management": case_management,
            "llm": llm,
            "osint_enrichment": osint_enrichment,
            "streaming": streaming,
        }

        if not include_sensitive:
            for k in checks:
                if checks[k].get("detail") and "path" in str(checks[k]["detail"]).lower():
                    checks[k] = dict(checks[k])
                    checks[k]["detail"] = "[filtered]"

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
            identity = self._check_identity()
            if identity["status"] == "error":
                failures.append(f"identity: {identity.get('detail') or identity['status']}")
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

        return {
            "ready": len(failures) == 0,
            "failures": failures,
            "generated_at": time.time(),
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
