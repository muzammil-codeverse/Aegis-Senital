from __future__ import annotations

import json

from scripts.evaluate_reid_models import evaluate_reid, load_query_gallery_layout


def test_reid_query_gallery_leakage_warning(tmp_path):
    query_path = tmp_path / "query.jsonl"
    gallery_path = tmp_path / "gallery.jsonl"
    query_path.write_text(
        json.dumps({"identity_id": "p1", "embedding": [1.0, 0.0], "image_path": "img_001.jpg"}) + "\n",
        encoding="utf-8",
    )
    gallery_path.write_text(
        "\n".join(
            [
                json.dumps({"identity_id": "p1", "embedding": [1.0, 0.0], "image_path": "img_001.jpg"}),
                json.dumps({"identity_id": "p2", "embedding": [0.0, 1.0], "image_path": "img_002.jpg"}),
            ]
        ),
        encoding="utf-8",
    )
    query_records, gallery_records = load_query_gallery_layout(tmp_path)
    metrics = evaluate_reid(query_records, gallery_records)
    assert metrics["overlap_or_leakage_detected"] is True
    assert metrics["embedding_failure_count"] == 0
