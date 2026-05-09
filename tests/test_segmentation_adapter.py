from __future__ import annotations

import numpy as np
import pytest

from inference.segmentation.config import SegmentationConfig
from inference.segmentation.sam2_adapter import Sam2SegmentationAdapter
from inference.segmentation.schemas import SEGMENTATION_PROVIDER_UNAVAILABLE


def test_sam2_adapter_unloaded_reports_provider_unavailable() -> None:
    adapter = Sam2SegmentationAdapter(SegmentationConfig())

    results = adapter.segment_boxes(
        np.zeros((32, 32, 3), dtype=np.uint8),
        [[1, 1, 10, 10]],
        ["phone"],
    )

    assert results[0].refinement_status == SEGMENTATION_PROVIDER_UNAVAILABLE
    assert results[0].label == "phone"
    assert results[0].mask is None


def test_sam2_load_missing_assets_raises() -> None:
    cfg = SegmentationConfig.from_dict({
        "enabled": True,
        "sam2": {
            "checkpoint_path": "missing/checkpoint.pt",
            "model_config": "missing/sam2.yaml",
        },
    })
    adapter = Sam2SegmentationAdapter(cfg)

    with pytest.raises(RuntimeError):
        adapter.load()
