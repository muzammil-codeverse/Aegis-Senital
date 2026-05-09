"""
FaceEnrollmentService — orchestrates face image upload, validation,
and enrollment record creation for an identity.

Security guarantees:
- File extensions are validated against an allowlist.
- Maximum upload size is enforced (default 8 MB).
- Saved filenames are sanitised to prevent path traversal.
- The returned enrollment record uses to_public_dict() — raw paths and
  embedding references are never returned to callers.
- The full path is resolved and verified to be within the image directory.

All thresholds are configurable via configs/runtime/identity_rules.yaml.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _load_identity_config() -> dict:
    """Load identity_rules.yaml; return empty dict on failure."""
    base = Path(__file__).resolve().parent.parent.parent.parent
    cfg_path = base / "configs" / "runtime" / "identity_rules.yaml"
    if cfg_path.exists():
        try:
            import yaml  # type: ignore
            with open(cfg_path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception as exc:
            logger.warning("Could not load identity_rules.yaml: %s", exc)
    return {}


class FaceEnrollmentService:
    """Service layer for face image upload, validation, and enrollment creation."""

    DEFAULT_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
    DEFAULT_MAX_FILE_MB = 8
    DEFAULT_MIN_QUALITY = 0.40

    def __init__(self, image_dir: Optional[str] = None) -> None:
        self._config = _load_identity_config()
        fe_cfg = self._config.get("face_enrollment", {})
        storage_cfg = self._config.get("storage", {})

        self._allowed_ext = set(
            fe_cfg.get("allowed_extensions", list(self.DEFAULT_ALLOWED_EXTENSIONS))
        )
        self._max_bytes = (
            int(fe_cfg.get("max_file_mb", self.DEFAULT_MAX_FILE_MB)) * 1024 * 1024
        )
        self._min_quality = float(
            fe_cfg.get("min_quality_score", self.DEFAULT_MIN_QUALITY)
        )

        if image_dir is None:
            base = Path(__file__).resolve().parent.parent.parent.parent
            rel = storage_cfg.get("enrollment_image_dir", "storage/enrollments/images")
            image_dir = str(base / rel)

        self._image_dir = Path(image_dir)
        self._image_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_extension(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in self._allowed_ext

    def _safe_filename(self, identity_id: str, original_filename: str) -> str:
        """Return a sanitised filename that cannot escape the image directory."""
        ext = Path(original_filename).suffix.lower()
        safe_name = f"{identity_id}_{int(time.time())}{ext}"
        # Strip any directory separators and parent-directory sequences
        return safe_name.replace("/", "").replace("\\", "").replace("..", "")

    # ------------------------------------------------------------------
    # Image storage
    # ------------------------------------------------------------------

    def _save_image(self, identity_id: str, filename: str, data: bytes) -> str:
        """
        Persist image bytes to the configured directory.

        Returns the plain filename (not an absolute path).
        Raises ValueError if the resolved destination escapes the image dir.
        """
        safe_name = self._safe_filename(identity_id, filename)
        dest = (self._image_dir / safe_name).resolve()
        image_dir_resolved = self._image_dir.resolve()
        if not str(dest).startswith(str(image_dir_resolved)):
            raise ValueError("Path traversal detected in enrollment image save")
        with open(dest, "wb") as fh:
            fh.write(data)
        # Return only the filename — never the absolute path
        return safe_name

    # ------------------------------------------------------------------
    # Quality estimation
    # ------------------------------------------------------------------

    def _compute_quality_score(self, data: bytes) -> Optional[float]:
        """
        Heuristic quality score based on file size.

        Production systems would replace this with a real face quality model.
        Returns None if data is unavailable.
        """
        if len(data) < 1_000:
            return 0.10
        if len(data) < 10_000:
            return 0.40
        return 0.75

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enroll_face(
        self,
        identity_id: Optional[str] = None,
        display_name: Optional[str] = None,
        image_filename: Optional[str] = None,
        image_data: Optional[bytes] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Validate, save, and record a face enrollment.

        Returns a structured response dict with status, identity_id,
        enrollment_id, quality_score, and identity fields.
        """
        from inference.identity.identity_profile_store import get_identity_store
        from inference.monitoring.metrics import get_metrics

        store = get_identity_store()
        metrics = get_metrics()

        # Create or resolve identity
        if identity_id is None:
            profile = store.create_identity(
                display_name=display_name, metadata=metadata or {}
            )
            identity_id = profile.identity_id
        else:
            profile = store.get_identity(identity_id)
            if profile is None:
                return {
                    "status": "error",
                    "detail": f"Identity {identity_id} not found",
                }

        # Validate file extension
        if image_filename and not self._validate_extension(image_filename):
            try:
                metrics.increment("face_enrollment_failures")
            except Exception:
                pass
            return {
                "status": "error",
                "detail": f"Invalid file type. Allowed: {sorted(self._allowed_ext)}",
                "code": 400,
            }

        # Validate file size
        if image_data and len(image_data) > self._max_bytes:
            try:
                metrics.increment("face_enrollment_failures")
            except Exception:
                pass
            return {
                "status": "error",
                "detail": f"File too large. Max {self._max_bytes // (1024 * 1024)} MB",
                "code": 400,
            }

        # Persist image
        saved_filename: Optional[str] = None
        if image_data and image_filename:
            try:
                saved_filename = self._save_image(identity_id, image_filename, image_data)
            except Exception as exc:
                logger.error("Failed to save enrollment image: %s", exc)
                try:
                    metrics.increment("face_enrollment_failures")
                except Exception:
                    pass
                return {"status": "error", "detail": "Failed to save image"}

        # Quality scoring
        quality_score: Optional[float] = None
        if image_data:
            quality_score = self._compute_quality_score(image_data)

        # Record enrollment (image_path is filename only — never absolute)
        enrollment = store.add_face_enrollment(
            identity_id=identity_id,
            image_path=saved_filename,
            quality_score=quality_score,
            metadata=metadata or {},
        )

        if enrollment is None:
            return {"status": "error", "detail": "Failed to create enrollment record"}

        try:
            metrics.increment("face_enrollments_created")
        except Exception:
            pass

        return {
            "status": "ok",
            "identity_id": identity_id,
            "enrollment_id": enrollment.enrollment_id,
            "quality_score": quality_score,
            "identity": profile.to_dict(),
        }

    def get_enrollment(self, enrollment_id: str) -> Optional[dict]:
        """Look up a single enrollment by ID; returns public-safe dict or None."""
        from inference.identity.identity_profile_store import get_identity_store

        store = get_identity_store()
        for _identity_id, enrollments in store._enrollments.items():
            for e in enrollments:
                if e.enrollment_id == enrollment_id:
                    return e.to_public_dict()
        return None

    def list_enrollments(self, identity_id: Optional[str] = None) -> list:
        """Return all enrollments (public-safe) optionally filtered by identity."""
        from inference.identity.identity_profile_store import get_identity_store

        store = get_identity_store()
        if identity_id:
            return [e.to_public_dict() for e in store.list_face_enrollments(identity_id)]
        results = []
        for _iid, enrollments in store._enrollments.items():
            for e in enrollments:
                results.append(e.to_public_dict())
        return results


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_service_instance: Optional[FaceEnrollmentService] = None
_service_lock = __import__("threading").Lock()


def get_enrollment_service() -> FaceEnrollmentService:
    """Return (or lazily create) the process-wide FaceEnrollmentService singleton."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = FaceEnrollmentService()
        return _service_instance
