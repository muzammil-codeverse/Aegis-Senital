from __future__ import annotations

import numpy as np

from inference.schemas import Detection, Event, FramePacket
from inference.segmentation.base import SegmentationAdapter
from inference.segmentation.config import SegmentationConfig
from inference.segmentation.mask_utils import mask_to_rle
from inference.segmentation.schemas import SEGMENTATION_SUCCESS, SegmentationResult
from inference.segmentation.segmentation_service import SegmentationService


class FakeAdapter(SegmentationAdapter):
    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def is_loaded(self) -> bool:
        return True

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
                mask_confidence=0.9,
                refinement_status=SEGMENTATION_SUCCESS,
            ))
        return results


def test_frame_packet_and_event_payload_receive_segmentation_metadata() -> None:
    service = SegmentationService(
        config=SegmentationConfig.from_dict({"enabled": True, "device": "cpu"}),
        adapter=FakeAdapter(),
    )
    packet = FramePacket(
        frame_id=7,
        image=np.zeros((32, 32, 3), dtype=np.uint8),
        detections=[Detection("weapon", [4, 4, 20, 20], 0.95, "weapon_model")],
    )
    event = Event(
        event_type="WEAPON_THREAT",
        severity="HIGH",
        priority_level="HIGH",
        contributing_tracks=[{"class_name": "weapon", "bbox": [4, 4, 20, 20]}],
    )

    payload = service.refine_frame(packet, events=[event])

    assert packet.metadata["segmentation"]["status"] == "success"
    assert packet.metadata["segmentation"]["mask_count"] == 1
    assert payload["masks"][0]["detection_id"] == packet.detections[0].detection_id
    assert event.to_dict()["segmentation"]["mask_count"] == 1
