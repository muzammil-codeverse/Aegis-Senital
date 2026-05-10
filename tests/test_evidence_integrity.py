from pathlib import Path

from app.services.evidence_integrity import compute_sha256, safe_evidence_metadata, verify_evidence_hash


def test_compute_and_verify_sha256(tmp_path):
    target = tmp_path / "evidence.txt"
    target.write_text("case evidence", encoding="utf-8")
    digest = compute_sha256(str(target))
    assert digest
    assert verify_evidence_hash(str(target), digest) is True


def test_safe_evidence_metadata_strips_sensitive_keys():
    cleaned = safe_evidence_metadata({
        "camera_id": "cam_01",
        "embedding": [1, 2, 3],
        "nested": {"raw_frame": "bytes", "severity": "high"},
    })
    assert cleaned["camera_id"] == "cam_01"
    assert "embedding" not in cleaned
    assert "raw_frame" not in cleaned["nested"]
