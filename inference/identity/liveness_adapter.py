from __future__ import annotations

import logging
import os
from typing import Any

from inference.identity.runtime_config import load_identity_config

logger = logging.getLogger(__name__)

# Integrations register here when a real anti-spoofing stack is wired in.
_REAL_LIVENESS_PROVIDERS: frozenset[str] = frozenset()


def liveness_provider_integrated(provider: str) -> bool:
    p = str(provider or "").strip().lower()
    if p in {"", "none", "pending", "disabled"}:
        return False
    return p in _REAL_LIVENESS_PROVIDERS


class LivenessProviderMissingError(RuntimeError):
    """Raised when liveness is enabled but no real provider is available."""


class LivenessAdapter:
    """Readiness-only liveness interface. No spoof verdicts are fabricated."""

    def __init__(self, config: dict[str, Any] | None = None, profile: str | None = None) -> None:
        identity_cfg = config or load_identity_config()
        self._cfg = identity_cfg.get("liveness", {})
        self._profile = (profile or os.environ.get("APP_ENV") or "development").lower()
        self.enabled = bool(self._cfg.get("enabled", False))
        self.provider = str(self._cfg.get("provider", "none") or "none").strip()
        self.fail_if_enabled_without_provider = bool(
            self._cfg.get("fail_if_enabled_without_provider", self._cfg.get("fail_if_enabled_missing", True))
        )
        self.operator_warning_when_disabled = bool(self._cfg.get("operator_warning_when_disabled", True))

    def _provider_available(self) -> bool:
        return liveness_provider_integrated(self.provider)

    def assert_ready(self) -> None:
        if not self.enabled:
            return
        if self._provider_available():
            return
        message = f"Liveness provider '{self.provider}' is not integrated (liveness unavailable)."
        if self.fail_if_enabled_without_provider:
            raise LivenessProviderMissingError(message)
        logger.warning("%s Policy requires operator awareness.", message)

    def evaluate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "provider": self.provider,
                "detail": "liveness disabled",
            }
        try:
            self.assert_ready()
        except LivenessProviderMissingError as exc:
            return {
                "enabled": True,
                "status": "unavailable",
                "provider": self.provider,
                "detail": str(exc),
            }
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
