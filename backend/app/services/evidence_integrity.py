from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


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


def compute_sha256(path: str) -> str:
    digest = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence_hash(path: str, expected_hash: str) -> bool:
    if not expected_hash:
        return False
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return False
    return compute_sha256(path) == expected_hash


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
