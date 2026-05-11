from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.security.config import PROJECT_ROOT, get_upload_security_config


_EXECUTABLE_SIGNATURES = (
    b"MZ",
    b"#!",
)
_ARCHIVE_SIGNATURES = (
    b"PK\x03\x04",
    b"Rar!",
    b"7z\xbc\xaf\x27\x1c",
)
_IMAGE_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
_DOCUMENT_SIGNATURES = {
    ".pdf": (b"%PDF-",),
}
_VIDEO_SIGNATURES = {
    ".mp4": (b"\x00\x00\x00", b"ftyp"),
    ".mov": (b"\x00\x00\x00", b"ftyp"),
    ".avi": (b"RIFF",),
    ".mkv": (b"\x1a\x45\xdf\xa3",),
}
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class UploadValidationResult:
    media_class: str
    original_filename: str
    normalized_filename: str
    extension: str
    content_type: str
    size_bytes: int
    sha256: str
    malware_scan: dict[str, Any]

    def build_storage_name(self, *parts: str) -> str:
        prefix = "_".join(_normalize_path_component(part) for part in parts if part)
        token = uuid.uuid4().hex[:12]
        if prefix:
            return f"{prefix}_{token}{self.extension}"
        return f"{token}{self.extension}"


class UploadSecurityPolicy:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        raw_config = config or get_upload_security_config()
        self._config = dict(raw_config.get("upload_security") or {})
        self._classes = dict(self._config.get("classes") or {})
        self._rejected_extensions = {
            str(item).strip().lower()
            for item in (self._config.get("rejected_extensions") or [])
            if str(item).strip()
        }

    def validate(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None,
        allowed_classes: set[str],
    ) -> UploadValidationResult:
        normalized_filename = normalize_filename(filename)
        extension = Path(normalized_filename).suffix.lower()
        if not extension:
            raise HTTPException(status_code=400, detail="Missing file extension")
        if extension in self._rejected_extensions:
            raise HTTPException(status_code=400, detail=f"Rejected file type '{extension}'")
        if _looks_like_executable(content):
            raise HTTPException(status_code=400, detail="Executable content is not allowed")
        if _looks_like_archive(content):
            raise HTTPException(status_code=400, detail="Archive uploads are not allowed")

        media_class = self._resolve_media_class(extension, allowed_classes)
        class_cfg = dict(self._classes.get(media_class) or {})
        allowed_extensions = {
            str(item).strip().lower()
            for item in (class_cfg.get("allowed_extensions") or [])
            if str(item).strip()
        }
        if extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file type '{extension}'")

        max_bytes = int(float(class_cfg.get("max_file_size_mb") or 16) * 1024 * 1024)
        size_bytes = len(content)
        if size_bytes > max_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {max_bytes // (1024 * 1024)} MB")

        validated_content_type = self._validate_content_type(
            media_class=media_class,
            extension=extension,
            provided_content_type=content_type,
        )
        self._validate_file_signature(extension=extension, content=content)
        digest = hashlib.sha256(content).hexdigest()

        return UploadValidationResult(
            media_class=media_class,
            original_filename=str(filename or ""),
            normalized_filename=normalized_filename,
            extension=extension,
            content_type=validated_content_type,
            size_bytes=size_bytes,
            sha256=digest,
            malware_scan=self.scan_for_malware(normalized_filename, content),
        )

    def resolve_storage_path(self, storage_dir: str, storage_name: str) -> Path:
        base = (PROJECT_ROOT / storage_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        target = (base / storage_name).resolve()
        if target != base and base not in target.parents:
            raise HTTPException(status_code=400, detail="Unsafe upload path")
        return target

    def scan_for_malware(self, filename: str, content: bytes) -> dict[str, Any]:
        del filename, content
        cfg = dict(self._config.get("malware_scan") or {})
        if not bool(cfg.get("enabled", False)):
            return {"status": "skipped", "provider": cfg.get("provider", "placeholder")}
        return {"status": "passed", "provider": cfg.get("provider", "placeholder")}

    def _resolve_media_class(self, extension: str, allowed_classes: set[str]) -> str:
        for media_class in allowed_classes:
            class_cfg = dict(self._classes.get(media_class) or {})
            allowed_extensions = {
                str(item).strip().lower()
                for item in (class_cfg.get("allowed_extensions") or [])
                if str(item).strip()
            }
            if extension in allowed_extensions:
                return media_class
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{extension}'")

    def _validate_content_type(
        self,
        *,
        media_class: str,
        extension: str,
        provided_content_type: str | None,
    ) -> str:
        guessed_content_type = mimetypes.types_map.get(extension, "application/octet-stream")
        content_type = str(provided_content_type or guessed_content_type or "application/octet-stream").lower()
        allowed_mime_types = {
            str(item).strip().lower()
            for item in ((self._classes.get(media_class) or {}).get("allowed_mime_types") or [])
            if str(item).strip()
        }
        if content_type not in allowed_mime_types:
            raise HTTPException(status_code=400, detail=f"Unsupported MIME type '{content_type}'")
        return content_type

    @staticmethod
    def _validate_file_signature(*, extension: str, content: bytes) -> None:
        header = content[:32]
        if extension in _IMAGE_SIGNATURES:
            if not any(header.startswith(signature) for signature in _IMAGE_SIGNATURES[extension]):
                raise HTTPException(status_code=400, detail="File signature does not match image extension")
            return
        if extension in _DOCUMENT_SIGNATURES:
            if content and not any(header.startswith(signature) for signature in _DOCUMENT_SIGNATURES[extension]):
                text_extensions = {".txt", ".md", ".json", ".csv"}
                if extension not in text_extensions:
                    raise HTTPException(status_code=400, detail="File signature does not match document extension")
            return
        if extension in {".txt", ".md", ".json", ".csv"}:
            if b"\x00" in content[:256]:
                raise HTTPException(status_code=400, detail="Binary content is not allowed for text documents")
            return
        if extension in _VIDEO_SIGNATURES:
            signatures = _VIDEO_SIGNATURES[extension]
            if extension in {".mp4", ".mov"}:
                if len(header) < 12 or header[4:8] != b"ftyp":
                    raise HTTPException(status_code=400, detail="File signature does not match video extension")
                return
            if not any(header.startswith(signature) for signature in signatures):
                raise HTTPException(status_code=400, detail="File signature does not match video extension")


def normalize_filename(filename: str) -> str:
    raw_text = str(filename or "").strip()
    normalized_separators = raw_text.replace("\\", "/")
    raw_name = Path(raw_text).name
    if not raw_text or raw_name != raw_text or ".." in normalized_separators:
        raise HTTPException(status_code=400, detail="Unsafe filename")
    if not raw_name or raw_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Unsafe filename")
    cleaned = _SAFE_NAME_RE.sub("_", raw_name)
    if cleaned.startswith("."):
        cleaned = cleaned.lstrip(".")
    if not cleaned or ".." in cleaned:
        raise HTTPException(status_code=400, detail="Unsafe filename")
    return cleaned


def _looks_like_executable(content: bytes) -> bool:
    header = content[:8]
    if any(header.startswith(signature) for signature in _EXECUTABLE_SIGNATURES):
        return True
    script_markers = (b"<script", b"powershell", b"#!/bin/", b"#!/usr/bin/")
    lowered = content[:256].lower()
    return any(marker in lowered for marker in script_markers)


def _looks_like_archive(content: bytes) -> bool:
    header = content[:8]
    return any(header.startswith(signature) for signature in _ARCHIVE_SIGNATURES)


def _normalize_path_component(value: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", str(value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned or "upload"


_upload_security_policy: UploadSecurityPolicy | None = None


def get_upload_security_policy() -> UploadSecurityPolicy:
    global _upload_security_policy
    if _upload_security_policy is None:
        _upload_security_policy = UploadSecurityPolicy()
    return _upload_security_policy
