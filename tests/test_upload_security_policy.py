from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.security.upload_policy import UploadSecurityPolicy, normalize_filename


def test_valid_upload_classes_are_accepted():
    policy = UploadSecurityPolicy()

    image = policy.validate(
        filename="frame.png",
        content=b"\x89PNG\r\n\x1a\n" + b"payload",
        content_type="image/png",
        allowed_classes={"image"},
    )
    document = policy.validate(
        filename="report.txt",
        content=b"incident summary",
        content_type="text/plain",
        allowed_classes={"document"},
    )
    video = policy.validate(
        filename="clip.mp4",
        content=b"\x00\x00\x00\x18ftypisom" + b"video",
        content_type="video/mp4",
        allowed_classes={"video"},
    )

    assert image.media_class == "image"
    assert document.media_class == "document"
    assert video.media_class == "video"
    assert image.sha256
    assert document.sha256
    assert video.sha256


def test_executable_upload_is_rejected():
    policy = UploadSecurityPolicy()

    with pytest.raises(HTTPException) as excinfo:
        policy.validate(
            filename="payload.exe",
            content=b"MZmalware",
            content_type="application/octet-stream",
            allowed_classes={"document"},
        )

    assert excinfo.value.status_code == 400


def test_path_traversal_filename_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        normalize_filename("../secret.png")

    assert excinfo.value.status_code == 400


def test_oversized_upload_is_rejected():
    policy = UploadSecurityPolicy()

    with pytest.raises(HTTPException) as excinfo:
        policy.validate(
            filename="oversized.png",
            content=b"\x89PNG\r\n\x1a\n" + (b"0" * (17 * 1024 * 1024)),
            content_type="image/png",
            allowed_classes={"image"},
        )

    assert excinfo.value.status_code == 413
