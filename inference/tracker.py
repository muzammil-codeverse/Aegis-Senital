from __future__ import annotations
from dataclasses import dataclass
from inference.schemas import DetectionResult


@dataclass
class _Track:
    track_id: int
    bbox: list       # [x1, y1, x2, y2]
    missed_frames: int = 0


class ByteTracker:
    """
    IoU-based multi-object tracker.
    Assigns persistent integer IDs across frames using greedy IoU matching.
    Create a new instance per video to ensure ID sequences start fresh.
    """

    def __init__(self, max_age: int = 30, iou_threshold: float = 0.3):
        self._max_age = max_age
        self._iou_threshold = iou_threshold
        self._tracks: list[_Track] = []
        self._next_id = 1

    def update(self, result: DetectionResult) -> DetectionResult:
        dets = result.objects

        if not dets:
            for t in self._tracks:
                t.missed_frames += 1
            self._tracks = [t for t in self._tracks if t.missed_frames < self._max_age]
            return result

        if not self._tracks:
            for obj in dets:
                obj.tracking_id = self._next_id
                self._tracks.append(_Track(track_id=self._next_id, bbox=obj.bbox))
                self._next_id += 1
            return result

        n_t, n_d = len(self._tracks), len(dets)
        iou_mat = [
            [self._iou(self._tracks[t].bbox, dets[d].bbox) for d in range(n_d)]
            for t in range(n_t)
        ]

        matched_t: set[int] = set()
        matched_d: set[int] = set()

        while True:
            best, bt, bd = 0.0, -1, -1
            for t in range(n_t):
                if t in matched_t:
                    continue
                for d in range(n_d):
                    if d in matched_d:
                        continue
                    if iou_mat[t][d] > best:
                        best, bt, bd = iou_mat[t][d], t, d
            if best < self._iou_threshold:
                break
            track = self._tracks[bt]
            track.bbox = dets[bd].bbox
            track.missed_frames = 0
            dets[bd].tracking_id = track.track_id
            matched_t.add(bt)
            matched_d.add(bd)

        for d in range(n_d):
            if d not in matched_d:
                dets[d].tracking_id = self._next_id
                self._tracks.append(_Track(track_id=self._next_id, bbox=dets[d].bbox))
                self._next_id += 1

        for t in range(n_t):
            if t not in matched_t:
                self._tracks[t].missed_frames += 1

        self._tracks = [t for t in self._tracks if t.missed_frames < self._max_age]
        return result

    @staticmethod
    def _iou(b1: list, b2: list) -> float:
        xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0
        inter = (xi2 - xi1) * (yi2 - yi1)
        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0
