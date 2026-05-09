from __future__ import annotations

import numpy as np
import pytest

from inference.schemas import Detection, Event, FramePacket
from inference.segmentation.base import SegmentationAdapter
from inference.segmentation.config import SegmentationConfig
from inference.segmentation.mask_utils import mask_to_rle
from inference.segmentation.schemas import SEGMENTATION_SUCCESS, SegmentationResult
from inference.segmentation.segmentation_service import SegmentationService


class FakeAdapter(SegmentationAdapter):
    def __init__(self, loaded: bool = True) -> None:
        self.loaded = loaded

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def is_loaded(self) -> bool:
        return self.loaded

    def segment_boxes(self, image, boxes, labels=None):
        labels = labels or []
        results = []
        for idx, box in enumerate(boxes):
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            x1, y1, x2, y2 = [int(v) for v in box]
            mask[y1:y2, x1:x2] = 1
            area = int(mask.sum())
            results.append(SegmentationResult(
                detection_id=f"provider_{idx}",
                label=labels[idx] if idx < len(labels) else "object",
                bbox=list(box),
                mask_encoding="rle",
                mask=mask_to_rle(mask),
                mask_area=area,
                bbox_area=area,
                mask_confidence=0.91,
                refinement_status=SEGMENTATION_SUCCESS,
            ))
        return results

    def health(self):
        return {"loaded": self.loaded, "status": "healthy" if self.loaded else "degraded", "device": "cpu"}


def _config(**overrides) -> SegmentationConfig:
    data = {
        "enabled": True,
        "provider": "sam2",
        "device": "cpu",
        "fail_open": True,
        "max_masks_per_frame": 20,
        "min_box_area_px": 64,
        "mask_encoding": "rle",
    }
    data.update(overrides)
    return SegmentationConfig.from_dict(data)


def test_provider_unavailable_degrades_without_crash() -> None:
    service = SegmentationService(config=_config(), adapter=FakeAdapter(loaded=False))
    packet = FramePacket(
        frame_id=1,
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=[Detection("phone", [2, 2, 20, 20], 0.8, "phone_model")],
    )

    payload = service.refine_frame(packet, events=[])

    assert payload["status"] == "degraded"
    assert payload["masks"][0]["refinement_status"] == "provider_unavailable"
    assert packet.detections[0].metadata["segmentation"]["failure_reason"]


def test_fail_closed_raises_when_provider_unavailable() -> None:
    service = SegmentationService(config=_config(fail_open=False), adapter=FakeAdapter(loaded=False))

    with pytest.raises(RuntimeError):
        service.refine(
            image=np.zeros((32, 32, 3), dtype=np.uint8),
            detections=[Detection("phone", [2, 2, 20, 20], 0.8, "phone_model")],
        )


def test_max_masks_per_frame_and_small_boxes_are_enforced() -> None:
    service = SegmentationService(
        config=_config(max_masks_per_frame=2, min_box_area_px=25),
        adapter=FakeAdapter(),
    )
    detections = [
        Detection("person", [0, 0, 2, 2], 0.9, "weapon_model"),
        Detection("weapon", [2, 2, 12, 12], 0.9, "weapon_model"),
        Detection("person", [14, 2, 24, 12], 0.8, "weapon_model"),
        Detection("phone", [2, 14, 12, 24], 0.7, "phone_model"),
    ]

    payload = service.refine(
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=detections,
    )

    statuses = [item["refinement_status"] for item in payload["masks"]]
    assert payload["mask_count"] == 2
    assert statuses.count("success") == 2
    assert statuses.count("skipped") == 2
    assert detections[0].metadata["segmentation"]["refinement_status"] == "skipped"


def test_event_payload_includes_segmentation_metadata() -> None:
    service = SegmentationService(config=_config(), adapter=FakeAdapter())
    detection = Detection("phone", [2, 2, 20, 20], 0.8, "phone_model")
    event = Event(
        event_type="PHONE_USAGE_RISK",
        severity="LOW",
        contributing_tracks=[{"class_name": "phone", "bbox": [2, 2, 20, 20]}],
    )

    payload = service.refine(
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=[detection],
        events=[event],
    )

    assert payload["status"] == "success"
    assert event.segmentation["mask_count"] == 1
    assert event.to_dict()["segmentation"]["masks"][0]["label"] == "phone"


def test_metrics_increment_on_success_failure_and_skipped() -> None:
    from inference.monitoring.metrics import get_metrics

    before = get_metrics().snapshot()
    service = SegmentationService(config=_config(max_masks_per_frame=1, min_box_area_px=25), adapter=FakeAdapter())
    service.refine(
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=[
            Detection("phone", [0, 0, 10, 10], 0.9, "phone_model"),
            Detection("person", [0, 0, 2, 2], 0.9, "weapon_model"),
        ],
    )
    unavailable = SegmentationService(config=_config(), adapter=FakeAdapter(loaded=False))
    unavailable.refine(
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=[Detection("phone", [0, 0, 10, 10], 0.9, "phone_model")],
    )
    after = get_metrics().snapshot()

    assert after["segmentation_success_total"] >= before["segmentation_success_total"] + 1
    assert after["segmentation_skipped_total"] >= before["segmentation_skipped_total"] + 1
    assert after["segmentation_failures_total"] >= before["segmentation_failures_total"] + 1
