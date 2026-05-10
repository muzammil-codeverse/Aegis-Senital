from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image

from inference.identity.enrollment import IdentityEnrollmentEngine
from inference.identity.identity_profile_store import IdentityProfileStore


class _FakeDB:
    def __init__(self) -> None:
        self.calls = []

    def persist_identity(self, **payload):
        self.calls.append(payload)


class _FakeAnalyzer:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def analyze(self, _image):
        return self._outputs.pop(0)


def _encode_image(value: int) -> bytes:
    y, x = np.indices((96, 96))
    image = np.stack(
        [
            ((x * 3 + value) % 255).astype(np.uint8),
            ((y * 5 + value) % 255).astype(np.uint8),
            (((x + y) * 7 + value) % 255).astype(np.uint8),
        ],
        axis=-1,
    )
    handle = BytesIO()
    Image.fromarray(image[:, :, ::-1], mode="RGB").save(handle, format="JPEG")
    return handle.getvalue()


def test_multi_image_enrollment_averages_embeddings(tmp_path):
    store = IdentityProfileStore(store_dir=str(tmp_path))
    db = _FakeDB()
    analyzer = _FakeAnalyzer(
        [
            {"embedding": [1.0, 0.0], "bbox": [0, 0, 96, 96], "detection_score": 0.95, "pose": [0.0, 0.0, 0.0]},
            {"embedding": [0.0, 1.0], "bbox": [0, 0, 96, 96], "detection_score": 0.95, "pose": [0.0, 0.0, 0.0]},
        ]
    )
    engine = IdentityEnrollmentEngine(
        db=db,
        store=store,
        config={"face": {"embedding_dim": 2, "min_face_size_px": 40, "min_detection_score": 0.6, "min_quality_score": 0.2}, "privacy": {"store_raw_faces": False}},
        face_analyzer=analyzer,
    )
    result = engine.enroll_person(
        [
            {"filename": "a.jpg", "data": _encode_image(140)},
            {"filename": "b.jpg", "data": _encode_image(150)},
        ],
        display_name="Operator Test",
    )
    assert result["status"] == "ok"
    assert result["accepted_images"] == 2
    assert db.calls
    embedding = db.calls[-1]["face_embedding"]
    assert len(embedding) == 2
    assert abs(sum(v * v for v in embedding) - 1.0) < 1e-4


def test_poor_enrollment_image_rejected(tmp_path):
    store = IdentityProfileStore(store_dir=str(tmp_path))
    db = _FakeDB()
    analyzer = _FakeAnalyzer(
        [
            {"embedding": [1.0, 0.0], "bbox": [0, 0, 20, 20], "detection_score": 0.20, "pose": [0.0, 0.0, 0.0]},
        ]
    )
    engine = IdentityEnrollmentEngine(
        db=db,
        store=store,
        config={"face": {"embedding_dim": 2, "min_face_size_px": 40, "min_detection_score": 0.6, "min_quality_score": 0.55}, "privacy": {"store_raw_faces": False}},
        face_analyzer=analyzer,
    )
    result = engine.enroll_person(
        [{"filename": "bad.jpg", "data": _encode_image(10)}],
        display_name="Rejected",
    )
    assert result["status"] == "error"
    assert result["accepted_images"] == 0
    assert result["rejected_images"] == 1
