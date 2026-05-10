import hashlib

import pytest

from app.services.osint_file_service import OsintFileService


def _config(tmp_path):
    return {
        "osint_enrichment": {
            "uploads": {
                "enabled": True,
                "storage_dir": str(tmp_path / "uploads"),
                "max_file_size_mb": 1,
                "allowed_extensions": [".txt", ".pdf", ".png"],
            }
        }
    }


def test_file_service_computes_sha256_and_uses_safe_storage_uri(tmp_path):
    service = OsintFileService(config=_config(tmp_path))
    content = b"manual analyst content"

    upload = service.save_upload(
        case_id="case_1",
        source_id="src_1",
        filename="notes.txt",
        content=content,
        content_type="text/plain",
        actor="operator",
    )

    assert upload.extension == ".txt"
    assert upload.sha256 == hashlib.sha256(content).hexdigest()
    assert upload.storage_uri.startswith(str("storage")) is False or upload.storage_uri.endswith(".txt")
    assert ".." not in upload.storage_uri


def test_file_service_blocks_path_traversal_and_executables(tmp_path):
    service = OsintFileService(config=_config(tmp_path))

    with pytest.raises(ValueError, match="Unsafe filename"):
        service.validate_upload("..\\bad.txt", 10)

    with pytest.raises(ValueError, match="Rejected file type"):
        service.validate_upload("payload.exe", 10)


def test_file_service_blocks_oversized_upload(tmp_path):
    service = OsintFileService(config=_config(tmp_path))

    with pytest.raises(ValueError, match="maximum size"):
        service.validate_upload("notes.txt", 2 * 1024 * 1024)
