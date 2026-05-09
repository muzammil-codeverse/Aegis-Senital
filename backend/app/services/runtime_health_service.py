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
        model_path = os.environ.get("AEGIS_OPEN_VOCAB_MODEL_PATH", "")
        allow_download = os.environ.get("AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD", "false").lower() == "true"
        if model_path and Path(model_path).exists():
            return {"status": "ok", "detail": "model path configured"}
        if allow_download:
            return {"status": "degraded", "detail": "model path not set; download enabled"}
        return {"status": "unavailable", "detail": "model path not configured and download disabled"}

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
