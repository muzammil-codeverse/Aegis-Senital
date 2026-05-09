from __future__ import annotations

from collections import defaultdict


class TimelineCorrelator:
    def correlate(self, records: list[dict], window_seconds: float = 30.0) -> list[dict]:
        by_identity: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            for identity_id in record.get("identity_ids", []):
                by_identity[str(identity_id)].append(record)

        correlations: list[dict] = []
        for identity_id, items in by_identity.items():
            items.sort(key=lambda item: item.get("timestamp", 0.0))
            for left, right in zip(items, items[1:]):
                if right.get("camera_id") == left.get("camera_id"):
                    continue
                delta = float(right.get("timestamp", 0.0)) - float(left.get("timestamp", 0.0))
                if 0.0 <= delta <= window_seconds:
                    correlations.append(
                        {
                            "identity_id": identity_id,
                            "source_camera": left.get("camera_id"),
                            "target_camera": right.get("camera_id"),
                            "delta_seconds": round(delta, 3),
                            "source_frame_id": left.get("frame_id"),
                            "target_frame_id": right.get("frame_id"),
                        }
                    )
        return correlations
