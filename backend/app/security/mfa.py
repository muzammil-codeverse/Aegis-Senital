from __future__ import annotations

from enum import Enum

from app.security.config import get_mfa_config


class MfaStatus(Enum):
    DISABLED = "disabled"
    REQUIRED = "required"
    VERIFIED = "verified"


class MfaProvider:
    def generate_challenge(self, user):
        raise NotImplementedError

    def verify_challenge(self, user, code):
        raise NotImplementedError


def mfa_status_for_user(user) -> MfaStatus:
    cfg = get_mfa_config()
    if not bool(cfg.get("enabled", False)):
        return MfaStatus.DISABLED
    required_roles = {str(role).lower() for role in cfg.get("required_roles", [])}
    if user and str(getattr(user, "role", "")).lower() in required_roles:
        provider = cfg.get("provider")
        if not provider:
            try:
                from inference.metrics import metrics
                metrics.increment("mfa_challenges_failed")
            except Exception:
                pass
            raise RuntimeError("MFA is enabled but no MFA provider is configured")
        try:
            from inference.metrics import metrics
            metrics.increment("mfa_challenges_created")
        except Exception:
            pass
        return MfaStatus.REQUIRED
    return MfaStatus.DISABLED
