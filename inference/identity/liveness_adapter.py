from __future__ import annotations

import logging
import os
from typing import Any

from inference.identity.runtime_config import load_identity_config

logger = logging.getLogger(__name__)


class LivenessProviderMissingError(RuntimeError):
    """Raised when liveness is enabled but no real provider is available."""


class LivenessAdapter:
    """Readiness-only liveness interface. No spoof verdicts are fabricated."""

    def __init__(self, config: dict[str, Any] | None = None, profile: str | None = None) -> None:
        identity_cfg = config or load_identity_config()
        self._cfg = identity_cfg.get("liveness", {})
        self._profile = (profile or os.environ.get("APP_ENV") or "development").lower()
        self.enabled = bool(self._cfg.get("enabled", False))
        self.provider = str(self._cfg.get("provider", "pending"))
        self.fail_if_enabled_missing = bool(self._cfg.get("fail_if_enabled_missing", True))

    def _provider_available(self) -> bool:
        return False

    def assert_ready(self) -> None:
        if not self.enabled:
            return
        if self._provider_available():
            return
        message = f"Liveness provider '{self.provider}' is not integrated."
        if self._profile == "production":
            raise LivenessProviderMissingError(message)
        logger.warning("%s Runtime remains degraded in development.", message)

    def evaluate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "provider": self.provider,
                "detail": "liveness disabled",
            }
        self.assert_ready()
        return {
            "enabled": True,
            "status": "degraded",
            "provider": self.provider,
            "detail": "provider interface only; no live liveness model integrated",
        }

    def get_health(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "provider": self.provider,
                "status": "disabled",
                "last_error": None,
            }
        try:
            self.assert_ready()
        except LivenessProviderMissingError as exc:
            return {
                "enabled": True,
                "provider": self.provider,
                "status": "failed",
                "last_error": str(exc),
            }
        return {
            "enabled": True,
            "provider": self.provider,
            "status": "degraded",
            "last_error": None,
        }
