from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.models.osint_models import CaseDocumentUpload
from app.repositories.osint_repository import load_osint_config
from app.security.upload_policy import get_upload_security_policy
from app.services.audit_log_service import get_audit_log_service
from app.services.evidence_integrity import (
    PROJECT_ROOT,
    describe_local_artifact,
    safe_evidence_metadata,
)


ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".json", ".csv", ".png", ".jpg", ".jpeg"}
REJECTED_EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".ps1", ".sh", ".js", ".py", ".dll", ".scr", ".zip"}


class OsintFileService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict((self._raw_config.get("osint_enrichment") or {}).get("uploads") or {})
        self._relative_storage_dir = Path(str(self._config.get("storage_dir") or "storage/osint_uploads"))
        self._storage_dir = (PROJECT_ROOT / self._relative_storage_dir).resolve()
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
            original_filename=validation.normalized_filename,
            safe_filename=safe_name,
            storage_uri=str((self._relative_storage_dir / safe_name).as_posix()),
            content_type=validation.content_type,
            extension=validation.extension,
            size_bytes=validation.size_bytes,
            hash_sha256=validation.sha256,
            sha256=validation.sha256,
            hash_verified=True,
            integrity_status="verified",
            created_by=actor,
            metadata={**dict(metadata or {}), "malware_scan": validation.malware_scan},
        )

    def build_download_response(
        self,
        *,
        case_id: str,
        source: Any,
        user: Any,
        request: Any = None,
    ) -> FileResponse:
        if str(getattr(source, "case_id", "")) != str(case_id):
            raise HTTPException(status_code=404, detail=f"Enrichment source '{getattr(source, 'source_id', '')}' not found for case '{case_id}'")
        if str(getattr(source, "source_type", "")).lower() == "external_link":
            raise HTTPException(status_code=400, detail="No local file artifact exists for this external link source")
        if str(getattr(source, "source_type", "")).lower() not in {"uploaded_document", "uploaded_image"}:
            raise HTTPException(status_code=400, detail="Source type does not provide a downloadable local artifact")
        artifact = describe_local_artifact(
            getattr(source, "storage_uri", None),
            expected_hash=getattr(source, "hash_sha256", None) or getattr(source, "metadata", {}).get("sha256"),
            allowed_roots=[self._storage_dir],
            content_type=getattr(source, "content_type", None),
            safe_filename=getattr(source, "safe_filename", None),
        )
        status = artifact.get("integrity_status") or "failed"
        if status == "missing_file":
            raise HTTPException(status_code=404, detail="OSINT source file is missing")
        if status in {"hash_mismatch", "failed"}:
            raise HTTPException(status_code=409, detail="OSINT source integrity verification failed")
        path = artifact.get("path")
        if not isinstance(path, Path):
            raise HTTPException(status_code=400, detail="No local file artifact exists for this source")
        headers = {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{getattr(source, "safe_filename", None) or path.name}"',
        }
        self._audit_download(
            user=user,
            request=request,
            source=source,
            metadata={
                "case_id": case_id,
                "source_id": getattr(source, "source_id", None),
                "integrity_status": status,
            },
        )
        return FileResponse(
            path=str(path),
            media_type=getattr(source, "content_type", None) or "application/octet-stream",
            filename=getattr(source, "safe_filename", None) or path.name,
            headers=headers,
        )

    @staticmethod
    def _audit_download(*, user: Any, request: Any, source: Any, metadata: dict[str, Any]) -> None:
        try:
            get_audit_log_service().record(
                "osint_source_file_downloaded",
                user=user,
                resource_type="osint_source",
                resource_id=str(getattr(source, "source_id", "") or ""),
                detail="osint source file downloaded",
                request=request,
                metadata=safe_evidence_metadata(metadata),
            )
        except Exception:
            pass

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


_OSINT_FILE_SERVICE: OsintFileService | None = None


def get_osint_file_service() -> OsintFileService:
    global _OSINT_FILE_SERVICE
    if _OSINT_FILE_SERVICE is None:
        _OSINT_FILE_SERVICE = OsintFileService()
    return _OSINT_FILE_SERVICE
