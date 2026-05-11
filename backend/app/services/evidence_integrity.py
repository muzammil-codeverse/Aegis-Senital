from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inference.config_runtime import load_runtime_config


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REMOTE_URI_PREFIXES = ("http://", "https://", "s3://", "gs://")
DEFAULT_EVIDENCE_CONFIG: dict[str, Any] = {
    "evidence": {
        "enabled": True,
        "storage": {
            "dev_backend": "local",
            "production_backend": "s3_or_filesystem",
            "local_dir": "storage/evidence",
            "require_production_storage": True,
        },
        "hashing": {
            "required_for_file_backed_evidence": True,
            "algorithm": "sha256",
            "verify_on_download": True,
            "verify_on_export": True,
        },
        "access": {
            "require_case_access": True,
            "require_evidence_access": True,
            "sensitive_headers": True,
            "audit_downloads": True,
        },
        "uploads": {
            "enabled": True,
            "max_file_size_mb": 250,
            "allowed_extensions": {
                "video": [".mp4", ".avi", ".mov", ".mkv"],
                "image": [".jpg", ".jpeg", ".png"],
                "document": [".pdf", ".txt", ".md", ".json", ".csv"],
            },
            "reject_archives": True,
            "reject_executables": True,
            "malware_scan_required_in_production": False,
            "malware_scan_placeholder": True,
        },
        "identity_assets": {
            "expose_raw_images_http": False,
            "admin_retrieval_enabled": False,
        },
        "osint_assets": {
            "protected_retrieval_enabled": True,
        },
        "retention": {
            "enabled": True,
            "default_days": 180,
            "archived_case_days": 365,
            "legal_hold_blocks_deletion": True,
        },
    }
}

_SENSITIVE_METADATA_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "bytes",
    "raw_image",
    "raw_frame",
    "image_blob",
    "binary",
    "content",
    "embedding",
    "embeddings",
    "face_embedding",
    "appearance_embedding",
    "file_path",
    "frame_path",
    "image_path",
    "path",
    "presigned_url",
    "secret",
    "signed_url",
    "snapshot_uri",
    "storage_uri",
    "token",
}
_SENSITIVE_METADATA_MARKERS = (
    "authorization",
    "embedding",
    "password",
    "secret",
    "token",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def load_evidence_config() -> dict[str, Any]:
    try:
        payload = load_runtime_config("evidence")
    except FileNotFoundError:
        return DEFAULT_EVIDENCE_CONFIG
    if not isinstance(payload, dict):
        return DEFAULT_EVIDENCE_CONFIG
    return _deep_merge(DEFAULT_EVIDENCE_CONFIG, payload)


def get_evidence_runtime_settings() -> dict[str, Any]:
    return dict(load_evidence_config().get("evidence") or {})


def get_evidence_storage_root(config: dict[str, Any] | None = None) -> Path:
    settings = dict((config or load_evidence_config()).get("evidence") or {})
    storage_cfg = dict(settings.get("storage") or {})
    local_dir = str(storage_cfg.get("local_dir") or "storage/evidence")
    root = (PROJECT_ROOT / local_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def compute_sha256(path: str) -> str:
    digest = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_bytes_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_evidence_hash(path: str, expected_hash: str) -> bool:
    if not expected_hash:
        return False
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return False
    return compute_sha256(path) == expected_hash


def is_remote_uri(storage_uri: str | None) -> bool:
    lowered = str(storage_uri or "").strip().lower()
    return lowered.startswith(REMOTE_URI_PREFIXES)


def resolve_local_storage_uri(storage_uri: str | None) -> Path | None:
    text = str(storage_uri or "").strip()
    if not text or is_remote_uri(text):
        return None
    path = Path(text)
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def is_path_within_roots(path: Path, allowed_roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in allowed_roots:
        candidate = root.resolve()
        if resolved == candidate or candidate in resolved.parents:
            return True
    return False


def ensure_managed_path(storage_uri: str | None, allowed_roots: list[Path]) -> Path | None:
    resolved = resolve_local_storage_uri(storage_uri)
    if resolved is None:
        return None
    if not is_path_within_roots(resolved, allowed_roots):
        raise ValueError("Resolved path escapes managed storage")
    return resolved


def guess_content_type(filename: str | None, provided_content_type: str | None = None) -> str:
    if provided_content_type:
        return str(provided_content_type).lower()
    guessed, _ = mimetypes.guess_type(str(filename or ""))
    return str(guessed or "application/octet-stream").lower()


def describe_local_artifact(
    storage_uri: str | None,
    *,
    expected_hash: str | None = None,
    allowed_roots: list[Path] | None = None,
    content_type: str | None = None,
    safe_filename: str | None = None,
) -> dict[str, Any]:
    if not storage_uri:
        return {
            "path": None,
            "size_bytes": None,
            "hash_sha256": None,
            "hash_verified": None,
            "integrity_status": "not_applicable",
            "content_type": content_type,
            "safe_filename": safe_filename,
            "last_verified_at": None,
        }

    try:
        resolved = ensure_managed_path(storage_uri, allowed_roots or [PROJECT_ROOT])
    except ValueError:
        return {
            "path": None,
            "size_bytes": None,
            "hash_sha256": None,
            "hash_verified": False,
            "integrity_status": "failed",
            "content_type": content_type,
            "safe_filename": safe_filename,
            "last_verified_at": None,
        }

    if resolved is None:
        return {
            "path": None,
            "size_bytes": None,
            "hash_sha256": None,
            "hash_verified": None,
            "integrity_status": "not_applicable",
            "content_type": content_type,
            "safe_filename": safe_filename,
            "last_verified_at": None,
        }
    if not resolved.exists() or not resolved.is_file():
        return {
            "path": resolved,
            "size_bytes": None,
            "hash_sha256": None,
            "hash_verified": False,
            "integrity_status": "missing_file",
            "content_type": content_type or guess_content_type(resolved.name),
            "safe_filename": safe_filename or resolved.name,
            "last_verified_at": _now_iso(),
        }

    digest = compute_sha256(str(resolved))
    verified = expected_hash is None or digest == expected_hash
    return {
        "path": resolved,
        "size_bytes": resolved.stat().st_size,
        "hash_sha256": digest,
        "hash_verified": verified,
        "integrity_status": "verified" if verified else "hash_mismatch",
        "content_type": content_type or guess_content_type(resolved.name),
        "safe_filename": safe_filename or resolved.name,
        "last_verified_at": _now_iso(),
    }


def safe_evidence_metadata(metadata: dict | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if lowered in _SENSITIVE_METADATA_KEYS or any(marker in lowered for marker in _SENSITIVE_METADATA_MARKERS):
            continue
        if isinstance(value, dict):
            cleaned[str(key)] = safe_evidence_metadata(value)
            continue
        if isinstance(value, (list, tuple)):
            cleaned[str(key)] = [_json_safe(item) for item in value]
            continue
        cleaned[str(key)] = _json_safe(value)
    return cleaned


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
