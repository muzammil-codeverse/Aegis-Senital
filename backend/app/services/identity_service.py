from __future__ import annotations

import logging
import os
from typing import Any

from inference.identity.global_identity_registry import get_global_registry
from inference.identity.liveness_adapter import LivenessAdapter
from inference.identity.runtime_config import load_identity_config
from ml.runtime.dependency_manager import get_identity_dependency_status

logger = logging.getLogger(__name__)


class IdentityService:
    def __init__(
        self,
        store: Any | None = None,
        db: Any | None = None,
        enrollment_engine: Any | None = None,
    ) -> None:
        from inference.identity.identity_profile_store import get_identity_store

        self._config = load_identity_config()
        self._store = store or get_identity_store()
        self._db = db
        self._enrollment = enrollment_engine
        self._liveness = LivenessAdapter(config=self._config, profile=os.environ.get("APP_ENV"))

    def _get_db(self) -> Any:
        if self._db is None:
            from inference.identity_db import get_db

            self._db = get_db()
        return self._db

    def _get_enrollment_engine(self) -> Any:
        if self._enrollment is None:
            from inference.identity.enrollment import IdentityEnrollmentEngine

            self._enrollment = IdentityEnrollmentEngine(
                db=self._get_db(),
                store=self._store,
                config=self._config,
            )
        return self._enrollment

    def enroll(
        self,
        images: list[dict[str, Any]],
        *,
        identity_id: str | None = None,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._get_enrollment_engine().enroll_person(
            images,
            identity_id=identity_id,
            display_name=display_name,
            metadata=metadata or {},
        )

    def list_enrollment_profiles(self, identity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return [
            profile.to_public_dict()
            for profile in self._store.list_enrollment_profiles(identity_id=identity_id, limit=limit)
        ]

    def get_enrollment_profile(self, enrollment_id: str) -> dict[str, Any] | None:
        profile = self._store.get_enrollment_profile(enrollment_id)
        return profile.to_public_dict() if profile else None

    def delete_enrollment_profile(self, enrollment_id: str) -> bool:
        return self._store.delete_enrollment_profile(enrollment_id)

    def list_face_enrollments(self, identity_id: str) -> list[dict[str, Any]]:
        return [enrollment.to_public_dict() for enrollment in self._store.list_face_enrollments(identity_id)]

    def get_health(self) -> dict[str, Any]:
        dependency_status = get_identity_dependency_status(profile=os.environ.get("APP_ENV"), config=self._config)
        analyzer_probe = getattr(self._enrollment, "_face_analyzer", "__missing__")
        face_runtime_loaded = (
            bool(dependency_status["face"]["available"])
            if analyzer_probe == "__missing__"
            else bool(analyzer_probe)
        )
        reid_runtime_loaded = bool(dependency_status["reid"]["available"])
        try:
            from app.services.video_service import _identity_fusion

            if _identity_fusion is not None:
                fusion_health = _identity_fusion.get_health()
                face_runtime_loaded = bool(fusion_health.get("face_loaded", face_runtime_loaded))
                reid_runtime_loaded = bool(fusion_health.get("reid_loaded", reid_runtime_loaded))
        except Exception:
            pass

        status = dependency_status["status"]
        face_enabled = bool(self._config.get("face", {}).get("enabled", False))
        reid_enabled = bool(self._config.get("reid", {}).get("enabled", False))
        if face_enabled and not face_runtime_loaded:
            status = "degraded" if bool(self._config.get("fail_open", True)) else "failed"
        if reid_enabled and not reid_runtime_loaded:
            status = "degraded" if bool(self._config.get("fail_open", True)) else "failed"

        failures_and_warnings = dependency_status["failures"] or dependency_status["warnings"]
        if face_enabled and not face_runtime_loaded:
            failures_and_warnings = [
                *failures_and_warnings,
                "identity.face runtime unavailable",
            ]
        if reid_enabled and not reid_runtime_loaded:
            failures_and_warnings = [
                *failures_and_warnings,
                "identity.reid runtime unavailable",
            ]

        health = {
            "enabled": bool(self._config.get("enabled", True)),
            "face_provider": self._config.get("face", {}).get("provider", "insightface"),
            "face_loaded": face_runtime_loaded,
            "reid_provider": self._config.get("reid", {}).get("provider", "osnet"),
            "reid_loaded": reid_runtime_loaded,
            "liveness_enabled": bool(self._config.get("liveness", {}).get("enabled", False)),
            "status": status,
            "last_error": "; ".join(failures_and_warnings) or None,
        }
        liveness_health = self._liveness.get_health()
        health["liveness_status"] = liveness_health["status"]
        try:
            health["persistence"] = get_global_registry().persistence_health()
        except Exception as exc:
            health["persistence"] = {
                "store": "identity_registry",
                "backend": "unknown",
                "status": "failed",
                "last_error": str(exc),
            }
        return health

    def list_global_identities(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return get_global_registry().list_records(status=status, limit=limit)


_identity_service: IdentityService | None = None


def get_identity_service() -> IdentityService:
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityService()
    return _identity_service
