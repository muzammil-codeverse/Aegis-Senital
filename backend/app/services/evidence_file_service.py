from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.models.case_models import CaseEvidence, EvidenceManifest, EvidenceVerificationResult
from app.models.security_models import UserAccount
from app.security.upload_policy import get_upload_security_policy
from app.services.audit_log_service import get_audit_log_service
from app.services.case_service import CaseService, get_case_service
from app.services.chain_of_custody_service import ChainOfCustodyService
from app.services.evidence_integrity import (
    PROJECT_ROOT,
    describe_local_artifact,
    get_evidence_runtime_settings,
    get_evidence_storage_root,
    guess_content_type,
    safe_evidence_metadata,
)
from app.services.rtsp_ingest_service import load_streaming_runtime_config


class EvidenceFileService:
    def __init__(
        self,
        *,
        case_service: CaseService | None = None,
        custody_service: ChainOfCustodyService | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._case_service = case_service or get_case_service()
        self._custody_service = custody_service or ChainOfCustodyService(case_service=self._case_service)
        self._raw_config = config or {"evidence": get_evidence_runtime_settings()}
        self._config = dict(self._raw_config.get("evidence") or get_evidence_runtime_settings())
        self._storage_root = get_evidence_storage_root(self._raw_config)
        self._upload_policy = get_upload_security_policy()
        self._managed_roots = self._build_managed_roots()

    def upload_case_evidence_file(
        self,
        case_id: str,
        file: Any,
        metadata: dict[str, Any] | None,
        user: UserAccount,
        *,
        request: Any = None,
    ) -> CaseEvidence:
        case = self._case_service.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        uploads_cfg = dict(self._config.get("uploads") or {})
        if not bool(uploads_cfg.get("enabled", True)):
            raise HTTPException(status_code=503, detail="Case evidence uploads are disabled")

        content = self._read_upload_bytes(file)
        max_bytes = int(float(uploads_cfg.get("max_file_size_mb") or 250) * 1024 * 1024)
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {max_bytes // (1024 * 1024)} MB")

        validation = self._upload_policy.validate(
            filename=getattr(file, "filename", None) or "upload.bin",
            content=content,
            content_type=getattr(file, "content_type", None),
            allowed_classes={"video", "image", "document"},
        )
        self._validate_upload_extension(validation.media_class, validation.extension)

        payload = dict(metadata or {})
        evidence_type = self._resolve_evidence_type(payload.get("evidence_type"), validation.media_class)
        evidence_id = f"evd_{uuid.uuid4().hex[:16]}"
        safe_filename = f"{evidence_id}{validation.extension}"
        verified_at = datetime.now(timezone.utc).isoformat()
        target_dir = (self._storage_root / case_id / evidence_id).resolve()
        target_path = (target_dir / safe_filename).resolve()
        if self._storage_root not in target_dir.parents and target_dir != self._storage_root:
            raise HTTPException(status_code=403, detail="Unsafe upload path")
        if target_dir not in target_path.parents:
            raise HTTPException(status_code=403, detail="Unsafe upload path")
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

        storage_uri = self._to_storage_uri(target_path)
        evidence = CaseEvidence(
            evidence_id=evidence_id,
            case_id=case_id,
            evidence_type=evidence_type,
            title=str(payload.get("title") or validation.normalized_filename).strip(),
            description=str(payload.get("description") or "").strip(),
            source_event_id=self._clean_optional(payload.get("source_event_id")),
            camera_id=self._clean_optional(payload.get("camera_id")),
            track_ids=self._normalize_list(payload.get("track_ids")),
            storage_uri=storage_uri,
            original_filename=validation.normalized_filename,
            safe_filename=safe_filename,
            content_type=validation.content_type,
            size_bytes=validation.size_bytes,
            created_by=user.username,
            hash_sha256=validation.sha256,
            hash_verified=True,
            integrity_status="verified",
            chain_status=self._resolve_chain_status(case, payload),
            last_verified_at=verified_at,
            metadata=safe_evidence_metadata(
                {
                    **payload,
                    "media_class": validation.media_class,
                    "malware_scan": validation.malware_scan,
                    "uploaded_via": "case_evidence_file_service",
                }
            ),
        )
        stored = self._case_service.store_evidence(
            evidence,
            actor=user.username,
            action="case_evidence_file_uploaded",
            detail="Protected case evidence file uploaded.",
            metadata={
                "evidence_id": evidence.evidence_id,
                "filename": evidence.safe_filename,
                "hash_sha256": evidence.hash_sha256,
                "size_bytes": evidence.size_bytes,
                "content_type": evidence.content_type,
            },
        )
        self._audit(
            "case_evidence_file_uploaded",
            user,
            request=request,
            resource_id=stored.evidence_id,
            metadata={
                "case_id": case_id,
                "evidence_id": stored.evidence_id,
                "filename": stored.safe_filename,
                "hash_sha256": stored.hash_sha256,
                "size_bytes": stored.size_bytes,
            },
        )
        return stored

    def get_case_evidence_file(
        self,
        case_id: str,
        evidence_id: str,
        user: UserAccount,
        *,
        request: Any = None,
    ) -> FileResponse:
        evidence = self._require_case_evidence(case_id, evidence_id)
        if not evidence.storage_uri:
            raise HTTPException(status_code=400, detail="Evidence does not include a local file artifact")
        verification = None
        if bool((self._config.get("hashing") or {}).get("verify_on_download", True)):
            verification = self.verify_case_evidence_file(case_id, evidence_id, user, request=request, trigger="download")
            if verification.integrity_status == "missing_file":
                raise HTTPException(status_code=404, detail="Evidence file is missing")
            if verification.integrity_status in {"hash_mismatch", "failed"}:
                raise HTTPException(status_code=409, detail="Evidence integrity verification failed")

        path = self._resolve_download_path(evidence)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Evidence file is missing")
        filename = evidence.safe_filename or evidence.original_filename or path.name
        headers = self._download_headers(filename)
        self._case_service.record_case_audit_event(
            case_id,
            action="case_evidence_file_downloaded",
            actor=user.username,
            detail="Protected case evidence file downloaded.",
            metadata={
                "evidence_id": evidence_id,
                "filename": filename,
                "integrity_status": verification.integrity_status if verification else evidence.integrity_status,
            },
        )
        self._audit(
            "case_evidence_file_downloaded",
            user,
            request=request,
            resource_id=evidence_id,
            metadata={"case_id": case_id, "filename": filename},
        )
        return FileResponse(
            path=str(path),
            media_type=evidence.content_type or guess_content_type(filename),
            filename=filename,
            headers=headers,
        )

    def verify_case_evidence_file(
        self,
        case_id: str,
        evidence_id: str,
        user: UserAccount,
        *,
        request: Any = None,
        trigger: str = "manual",
    ) -> EvidenceVerificationResult:
        evidence = self._require_case_evidence(case_id, evidence_id)
        if not evidence.storage_uri:
            result = EvidenceVerificationResult(
                case_id=case_id,
                evidence_id=evidence_id,
                storage_uri=None,
                expected_hash_sha256=evidence.hash_sha256,
                computed_hash_sha256=None,
                hash_verified=None,
                integrity_status="not_applicable",
                size_bytes=evidence.size_bytes,
                content_type=evidence.content_type,
                metadata={"trigger": trigger},
            )
            self._record_verification(evidence, result, user, request=request, trigger=trigger)
            return result

        try:
            artifact = describe_local_artifact(
                evidence.storage_uri,
                expected_hash=evidence.hash_sha256,
                allowed_roots=self._managed_roots,
                content_type=evidence.content_type,
                safe_filename=evidence.safe_filename,
            )
        except Exception as exc:
            artifact = {
                "path": None,
                "size_bytes": None,
                "hash_sha256": None,
                "hash_verified": False,
                "integrity_status": "failed",
                "content_type": evidence.content_type,
                "safe_filename": evidence.safe_filename,
                "last_verified_at": None,
                "error": str(exc),
            }
        result = EvidenceVerificationResult(
            case_id=case_id,
            evidence_id=evidence_id,
            storage_uri=evidence.storage_uri,
            expected_hash_sha256=evidence.hash_sha256,
            computed_hash_sha256=artifact.get("hash_sha256"),
            hash_verified=artifact.get("hash_verified"),
            integrity_status=artifact.get("integrity_status") or "failed",
            size_bytes=artifact.get("size_bytes") or evidence.size_bytes,
            content_type=artifact.get("content_type") or evidence.content_type,
            metadata=safe_evidence_metadata(
                {
                    "trigger": trigger,
                    "managed_path": str(artifact.get("path")) if artifact.get("path") else None,
                    "error": artifact.get("error"),
                }
            ),
        )
        updates = {
            "size_bytes": result.size_bytes,
            "content_type": result.content_type,
            "hash_sha256": evidence.hash_sha256 or result.computed_hash_sha256,
            "hash_verified": result.hash_verified,
            "integrity_status": result.integrity_status,
            "last_verified_at": result.verified_at,
        }
        self._case_service.update_evidence(evidence_id, updates, actor=user.username)
        refreshed = self._case_service.get_evidence(evidence_id)
        if refreshed is not None:
            evidence = refreshed
        self._record_verification(evidence, result, user, request=request, trigger=trigger)
        return result

    def build_evidence_manifest(
        self,
        case_id: str,
        user: UserAccount,
        *,
        request: Any = None,
    ) -> EvidenceManifest:
        manifest = self._custody_service.build_manifest(case_id, generated_by=user.username)
        self._case_service.record_case_audit_event(
            case_id,
            action="case_evidence_manifest_exported",
            actor=user.username,
            detail="Case evidence manifest exported.",
            metadata={"evidence_count": len(manifest.evidence_items)},
        )
        self._audit(
            "case_evidence_manifest_exported",
            user,
            request=request,
            resource_id=case_id,
            metadata={"case_id": case_id, "evidence_count": len(manifest.evidence_items)},
        )
        return manifest

    def _record_verification(
        self,
        evidence: CaseEvidence,
        result: EvidenceVerificationResult,
        user: UserAccount,
        *,
        request: Any = None,
        trigger: str,
    ) -> None:
        metadata = {
            "evidence_id": evidence.evidence_id,
            "expected_hash_sha256": result.expected_hash_sha256,
            "computed_hash_sha256": result.computed_hash_sha256,
            "integrity_status": result.integrity_status,
            "trigger": trigger,
        }
        self._case_service.record_case_audit_event(
            evidence.case_id,
            action="case_evidence_file_verified",
            actor=user.username,
            detail="Case evidence file integrity verified.",
            metadata=metadata,
        )
        self._audit("case_evidence_file_verified", user, request=request, resource_id=evidence.evidence_id, metadata={"case_id": evidence.case_id, **metadata})
        if result.integrity_status in {"hash_mismatch", "failed"}:
            self._case_service.record_case_audit_event(
                evidence.case_id,
                action="case_evidence_tamper_detected",
                actor=user.username,
                detail="Evidence integrity issue detected.",
                metadata=metadata,
            )
            self._audit("case_evidence_tamper_detected", user, request=request, resource_id=evidence.evidence_id, metadata={"case_id": evidence.case_id, **metadata})

    def _resolve_evidence_type(self, requested_type: Any, media_class: str) -> str:
        default_by_class = {
            "video": "upload",
            "image": "image",
            "document": "document",
        }
        allowed_by_class = {
            "video": {"upload", "clip"},
            "image": {"image", "frame", "identity", "osint", "upload"},
            "document": {"document", "osint", "system_report", "upload"},
        }
        requested = str(requested_type or "").strip().lower()
        if not requested:
            return default_by_class.get(media_class, "upload")
        if requested not in allowed_by_class.get(media_class, set()):
            raise HTTPException(status_code=400, detail=f"Evidence type '{requested}' is not valid for {media_class} uploads")
        return requested

    def _validate_upload_extension(self, media_class: str, extension: str) -> None:
        allowed = {
            str(item).lower()
            for item in (dict((self._config.get("uploads") or {}).get("allowed_extensions") or {}).get(media_class) or [])
        }
        if allowed and extension.lower() not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file type '{extension}'")

    def _resolve_chain_status(self, case: Any, metadata: dict[str, Any]) -> str:
        requested = str(metadata.get("chain_status") or "").strip().lower()
        if requested in {"active", "archived", "legal_hold", "deleted"}:
            return requested
        if bool(metadata.get("legal_hold")) or bool((case.metadata or {}).get("legal_hold")):
            return "legal_hold"
        if str(case.status).lower() == "archived":
            return "archived"
        return "active"

    def _require_case_evidence(self, case_id: str, evidence_id: str) -> CaseEvidence:
        evidence = self._case_service.get_evidence(evidence_id)
        if evidence is None or evidence.case_id != case_id:
            raise HTTPException(status_code=404, detail=f"Evidence '{evidence_id}' not found for case '{case_id}'")
        return evidence

    def _resolve_download_path(self, evidence: CaseEvidence) -> Path:
        artifact = describe_local_artifact(
            evidence.storage_uri,
            expected_hash=evidence.hash_sha256,
            allowed_roots=self._managed_roots,
            content_type=evidence.content_type,
            safe_filename=evidence.safe_filename,
        )
        path = artifact.get("path")
        if not isinstance(path, Path):
            raise HTTPException(status_code=400, detail="No local file artifact exists")
        return path

    def _build_managed_roots(self) -> list[Path]:
        roots = {self._storage_root.resolve()}
        try:
            replay_cfg = dict((load_streaming_runtime_config().get("streaming") or {}).get("replay") or {})
            replay_dir = (PROJECT_ROOT / str(replay_cfg.get("output_dir") or "storage/replay")).resolve()
            roots.add(replay_dir)
        except Exception:
            pass
        try:
            from inference.config_runtime import load_runtime_config

            uv_cfg = dict(load_runtime_config("uploaded_video").get("uploaded_video") or {})
            storage = dict(uv_cfg.get("storage") or {})
            processed = (PROJECT_ROOT / str(storage.get("processed_dir") or "storage/uploaded_video_results")).resolve()
            uploads = (PROJECT_ROOT / str(storage.get("root_dir") or "storage/uploaded_videos")).resolve()
            roots.add(processed)
            roots.add(uploads)
        except Exception:
            roots.add((PROJECT_ROOT / "storage/uploaded_video_results").resolve())
            roots.add((PROJECT_ROOT / "storage/uploaded_videos").resolve())
        return list(roots)

    def _download_headers(self, filename: str) -> dict[str, str]:
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if bool((self._config.get("access") or {}).get("sensitive_headers", True)):
            headers["Cache-Control"] = "no-store"
            headers["X-Content-Type-Options"] = "nosniff"
        return headers

    def _to_storage_uri(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path.resolve())

    @staticmethod
    def _read_upload_bytes(file: Any) -> bytes:
        if hasattr(file, "file") and hasattr(file.file, "read"):
            file.file.seek(0)
            return file.file.read()
        if hasattr(file, "read"):
            data = file.read()
            if isinstance(data, bytes):
                return data
        if isinstance(file, bytes):
            return file
        raise HTTPException(status_code=400, detail="Unsupported upload payload")

    @staticmethod
    def _normalize_list(value: Any) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple, set)) else [value]
        result: list[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    @staticmethod
    def _clean_optional(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _audit(action: str, user: UserAccount, *, request: Any = None, resource_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        try:
            get_audit_log_service().record(
                action,
                user=user,
                resource_type="evidence",
                resource_id=resource_id,
                detail=action.replace("_", " "),
                request=request,
                metadata=safe_evidence_metadata(metadata or {}),
            )
        except Exception:
            pass


_EVIDENCE_FILE_SERVICE: EvidenceFileService | None = None


def get_evidence_file_service() -> EvidenceFileService:
    global _EVIDENCE_FILE_SERVICE
    if _EVIDENCE_FILE_SERVICE is None:
        _EVIDENCE_FILE_SERVICE = EvidenceFileService()
    return _EVIDENCE_FILE_SERVICE
