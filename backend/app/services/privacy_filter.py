from __future__ import annotations

import copy
import os
from pathlib import PurePath
from typing import Any

from app.models.security_models import PrivacyPolicy, UserAccount
from app.security.config import get_privacy_config


SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "authorization",
    "embedding",
    "embeddings",
    "embedding_vector",
    "embedding_vector_ref",
    "image_path",
    "enrollment_image_path",
    "file_path",
}


class PrivacyFilter:
    def __init__(self, policy: PrivacyPolicy | None = None) -> None:
        self.policy = policy or PrivacyPolicy.from_dict(get_privacy_config())

    def _sanitize(self, payload: Any) -> Any:
        if isinstance(payload, list):
            return [self._sanitize(item) for item in payload]
        if isinstance(payload, tuple):
            return [self._sanitize(item) for item in payload]
        if not isinstance(payload, dict):
            if isinstance(payload, str) and self._looks_like_absolute_path(payload):
                return PurePath(payload).name
            return payload

        cleaned = {}
        for key, value in payload.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or "embedding" in lowered:
                continue
            if lowered.endswith("_path") or lowered == "path":
                if not self.policy.allow_raw_enrollment_image_access:
                    continue
            if isinstance(value, str) and self._looks_like_absolute_path(value):
                continue
            cleaned[key_text] = self._sanitize(value)
        return cleaned

    @staticmethod
    def _looks_like_absolute_path(value: str) -> bool:
        return os.path.isabs(value) or (len(value) > 2 and value[1] == ":" and value[2:3] in {"\\", "/"})

    @staticmethod
    def _user_role(user: UserAccount | None) -> str | None:
        return user.role if user else None

    def filter_identity_payload(self, payload: Any, user: UserAccount | None) -> Any:
        result = self._sanitize(copy.deepcopy(payload))
        role = self._user_role(user)
        if self.policy.mask_identity_display_for_viewer and role == "viewer":
            self._mask_identity_names(result)
        return result

    def filter_watchlist_payload(self, payload: Any, user: UserAccount | None) -> Any:
        result = self._sanitize(copy.deepcopy(payload))
        role = self._user_role(user)
        if self.policy.hide_watchlist_reason_for_operator and role == "operator":
            self._remove_key_recursive(result, "reason")
        return result

    def filter_alert_payload(self, payload: Any, user: UserAccount | None) -> Any:
        result = self._sanitize(copy.deepcopy(payload))
        if self.policy.mask_identity_display_for_viewer and self._user_role(user) == "viewer":
            self._mask_identity_names(result)
        return result

    def filter_incident_payload(self, payload: Any, user: UserAccount | None) -> Any:
        result = self._sanitize(copy.deepcopy(payload))
        if self.policy.mask_identity_display_for_viewer and self._user_role(user) == "viewer":
            self._mask_identity_names(result)
        return result

    def _mask_identity_names(self, payload: Any) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._mask_identity_names(item)
            return
        if not isinstance(payload, dict):
            return
        if "display_name" in payload and payload.get("display_name"):
            identity_id = str(payload.get("identity_id") or "")
            suffix = identity_id[-6:] if identity_id else "masked"
            payload["display_name"] = f"Identity {suffix}"
        for value in payload.values():
            self._mask_identity_names(value)

    def _remove_key_recursive(self, payload: Any, key_name: str) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._remove_key_recursive(item, key_name)
            return
        if not isinstance(payload, dict):
            return
        payload.pop(key_name, None)
        for value in payload.values():
            self._remove_key_recursive(value, key_name)


_privacy_filter: PrivacyFilter | None = None


def get_privacy_filter() -> PrivacyFilter:
    global _privacy_filter
    if _privacy_filter is None:
        _privacy_filter = PrivacyFilter()
    return _privacy_filter


def filter_identity_payload(payload: Any, user: UserAccount | None) -> Any:
    return get_privacy_filter().filter_identity_payload(payload, user)


def filter_watchlist_payload(payload: Any, user: UserAccount | None) -> Any:
    return get_privacy_filter().filter_watchlist_payload(payload, user)


def filter_alert_payload(payload: Any, user: UserAccount | None) -> Any:
    return get_privacy_filter().filter_alert_payload(payload, user)


def filter_incident_payload(payload: Any, user: UserAccount | None) -> Any:
    return get_privacy_filter().filter_incident_payload(payload, user)
