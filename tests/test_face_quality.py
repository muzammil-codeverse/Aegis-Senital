from __future__ import annotations

import numpy as np

from inference.identity.face_quality import score_face_quality


def _textured_face(size: int = 96) -> np.ndarray:
    y, x = np.indices((size, size))
    image = np.stack(
        [
            ((x * 7 + y * 3) % 255).astype(np.uint8),
            ((x * 5 + y * 11) % 255).astype(np.uint8),
            ((x * 13 + y * 2) % 255).astype(np.uint8),
        ],
        axis=-1,
    )
    return image


def test_good_quality_face_accepted():
    result = score_face_quality(
        _textured_face(),
        detection_score=0.95,
        pose=[0.0, 0.0, 0.0],
        embedding=[1.0] + [0.0] * 511,
    )
    assert result["is_usable"] is True
    assert result["quality_score"] >= 0.55


def test_low_quality_face_rejected():
    tiny_dark = np.zeros((20, 20, 3), dtype=np.uint8)
    result = score_face_quality(
        tiny_dark,
        detection_score=0.20,
        pose=[60.0, 30.0, 0.0],
        embedding=[0.0] * 512,
    )
    assert result["is_usable"] is False
    assert "face_too_small" in result["reasons"]
    assert "low_detection_confidence" in result["reasons"]
