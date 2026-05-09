from __future__ import annotations

from inference.segmentation.config import SegmentationConfig
from inference.segmentation.base import SegmentationAdapter
from inference.segmentation.segmentation_service import SegmentationService


class FakeAdapter(SegmentationAdapter):
    def __init__(self, loaded: bool) -> None:
        self.loaded = loaded

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def is_loaded(self) -> bool:
        return self.loaded

    def segment_boxes(self, image, boxes, labels=None):
        return []

    def health(self):
        return {"loaded": self.loaded, "status": "healthy" if self.loaded else "degraded", "device": "cpu"}


def test_health_disabled() -> None:
    service = SegmentationService(
        config=SegmentationConfig.from_dict({"enabled": False}),
        adapter=FakeAdapter(loaded=False),
    )

    health = service.get_health()

    assert health["enabled"] is False
    assert health["status"] == "disabled"


def test_health_degraded_when_enabled_but_unloaded() -> None:
    service = SegmentationService(
        config=SegmentationConfig.from_dict({"enabled": True, "device": "cpu"}),
        adapter=FakeAdapter(loaded=False),
    )

    health = service.get_health()

    assert health["enabled"] is True
    assert health["loaded"] is False
    assert health["status"] == "degraded"


def test_health_healthy_when_loaded() -> None:
    service = SegmentationService(
        config=SegmentationConfig.from_dict({"enabled": True, "device": "cpu"}),
        adapter=FakeAdapter(loaded=True),
    )

    health = service.get_health()

    assert health["loaded"] is True
    assert health["status"] == "healthy"
