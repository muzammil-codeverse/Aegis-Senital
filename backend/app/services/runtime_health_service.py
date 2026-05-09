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
            from core.event_bus.event_bus import EventBus  # noqa: F401
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

    def get_health(self, include_sensitive: bool = False) -> dict:
        """Return aggregated health status for all subsystems."""
        checks = {
            "database": self._check_database(),
            "redis": self._check_redis(),
            "gpu": self._check_gpu(),
            "open_vocab": self._check_open_vocab(),
            "storage": self._check_storage(),
            "model_registry": self._check_model_registry(),
            "event_bus": self._check_event_bus(),
            "security": self._check_security(),
        }

        if not include_sensitive:
            for k in checks:
                if checks[k].get("detail") and "path" in str(checks[k]["detail"]).lower():
                    checks[k] = dict(checks[k])
                    checks[k]["detail"] = "[filtered]"

        statuses = [c["status"] for c in checks.values()]
        if "error" in statuses:
            overall = "error"
        elif "degraded" in statuses or "unavailable" in statuses:
            overall = "degraded"
        else:
            overall = "ok"

        return {
            "status": overall,
            "generated_at": time.time(),
            "checks": checks,
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
