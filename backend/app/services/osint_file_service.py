from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from app.models.osint_models import CaseDocumentUpload
from app.repositories.osint_repository import load_osint_config
from app.security.upload_policy import get_upload_security_policy


ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".json", ".csv", ".png", ".jpg", ".jpeg"}
REJECTED_EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".ps1", ".sh", ".js", ".py", ".dll", ".scr", ".zip"}


class OsintFileService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict((self._raw_config.get("osint_enrichment") or {}).get("uploads") or {})
        self._relative_storage_dir = Path(str(self._config.get("storage_dir") or "storage/osint_uploads"))
        self._storage_dir = self._relative_storage_dir.resolve()
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def validate_upload(self, filename: str, size_bytes: int) -> str:
        if not bool(self._config.get("enabled", True)):
            self._increment_metric("osint_safety_blocks_total")
            raise RuntimeError("OSINT uploads are disabled")
        raw_name = str(filename or "").strip()
        if not raw_name or Path(raw_name).name != raw_name or ".." in raw_name.replace("\\", "/"):
            self._increment_metric("osint_upload_rejections_total")
            self._increment_metric("osint_safety_blocks_total")
            raise ValueError("Unsafe filename")
        ext = Path(filename or "").suffix.lower()
        if ext in REJECTED_EXECUTABLE_EXTENSIONS:
            self._increment_metric("osint_upload_rejections_total")
            self._increment_metric("osint_safety_blocks_total")
            raise ValueError(f"Rejected file type '{ext}'")
        allowed = {str(item).lower() for item in (self._config.get("allowed_extensions") or sorted(ALLOWED_UPLOAD_EXTENSIONS))}
        if ext not in allowed:
            self._increment_metric("osint_upload_rejections_total")
            raise ValueError(f"Unsupported file type '{ext}'")
        max_bytes = int(float(self._config.get("max_file_size_mb") or 25) * 1024 * 1024)
        if size_bytes > max_bytes:
            self._increment_metric("osint_upload_rejections_total")
            raise ValueError(f"File exceeds maximum size of {self._config.get('max_file_size_mb') or 25} MB")
        return ext

    def save_upload(
        self,
        *,
        case_id: str,
        source_id: str,
        filename: str,
        content: bytes,
        content_type: str | None,
        actor: str,
        metadata: dict[str, Any] | None = None,
    ) -> CaseDocumentUpload:
        self.validate_upload(filename, len(content))
        validation = get_upload_security_policy().validate(
            filename=filename,
            content=content,
            content_type=content_type,
            allowed_classes={"image", "document"},
        )
        safe_name = validation.build_storage_name(case_id, source_id)
        target = (self._storage_dir / safe_name).resolve()
        if self._storage_dir not in target.parents and target != self._storage_dir:
            self._increment_metric("osint_upload_rejections_total")
            self._increment_metric("osint_safety_blocks_total")
            raise ValueError("Unsafe upload path")
        target.write_bytes(content)
        return CaseDocumentUpload(
            source_id=source_id,
            case_id=case_id,
            filename=validation.normalized_filename,
            storage_uri=str((self._relative_storage_dir / safe_name).as_posix()),
            content_type=validation.content_type,
            extension=validation.extension,
            size_bytes=validation.size_bytes,
            sha256=validation.sha256,
            created_by=actor,
            metadata={**dict(metadata or {}), "malware_scan": validation.malware_scan},
        )

    @staticmethod
    def _increment_metric(name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics

            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics as system_metrics

            system_metrics.increment(name, count)
        except Exception:
            pass
