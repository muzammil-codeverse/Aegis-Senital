from __future__ import annotations
import json
import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Spatial overlap threshold: detections from different models that overlap
# this much are treated as describing the same real-world object.
_OVERLAP_IOU_THRESHOLD = 0.40

# Fusion weight components (must sum to 1.0)
_W_CONFIDENCE = 0.50   # raw model output confidence
_W_CONTEXT    = 0.30   # contextual signal from active tracks
_W_HISTORY    = 0.20   # track stability (temporal persistence)


def _iou(b1: list, b2: list) -> float:
    xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    inter = (xi2 - xi1) * (yi2 - yi1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


class ModelFusionEngine:
    """
    Resolves conflicts between simultaneous multi-model detections.

    When the weapon model and phone model both fire on overlapping bbox
    regions, a naive merge double-counts the object and may create
    contradictory Track updates.  This engine runs once per FramePacket,
    before tracking:

      1. Identify overlapping bbox pairs from *different* source models
         (IoU >= _OVERLAP_IOU_THRESHOLD).
      2. Score each detection in the conflicting pair:
             score = W_conf*confidence + W_ctx*context + W_hist*history
         where:
           confidence  raw model output ∈ [0, 1]
           context     1.0 if established same-class tracks exist (scene
                       context corroborates this class); 0.5 otherwise
           history     best stability_score among same-class active tracks;
                       rewards detections the tracker has seen before
      3. Discard the lower-scoring detection; keep the winner unchanged.
      4. All non-conflicting detections pass through untouched.

    Detections from the *same* model are not compared (false positives
    from one model are handled by NMS inside the model itself).
    """

    def fuse(
        self,
        detections: list,
        active_tracks: list | None = None,
    ) -> list:
        """
        Return a deduplicated detection list with spatial conflicts resolved.

        Parameters
        ----------
        detections      list[Detection] from DetectionEngine.predict()
        active_tracks   list[Track] from the last tracker.update(), used for
                        history-based scoring. Pass None for the first frame.

        Returns
        -------
        list[Detection] — same objects, some removed if they conflicted.
        """
        if len(detections) < 2:
            return list(detections)

        track_map = self._build_track_map(active_tracks or [])
        n = len(detections)
        discard: set[int] = set()

        for i in range(n):
            if i in discard:
                continue
            for j in range(i + 1, n):
                if j in discard:
                    continue
                d1, d2 = detections[i], detections[j]
                # Only resolve conflicts across different source models
                if d1.source_model == d2.source_model:
                    continue
                if _iou(d1.bbox, d2.bbox) < _OVERLAP_IOU_THRESHOLD:
                    continue

                s1 = self._fusion_score(d1, track_map)
                s2 = self._fusion_score(d2, track_map)
                loser_idx = j if s1 >= s2 else i
                discard.add(loser_idx)

                winner = detections[i if loser_idx == j else j]
                logger.debug(json.dumps({
                    "event": "fusion_conflict_resolved",
                    "winner_class": winner.class_name,
                    "winner_model": winner.source_model,
                    "winner_score": round(max(s1, s2), 3),
                    "loser_class": detections[loser_idx].class_name,
                    "loser_model": detections[loser_idx].source_model,
                    "loser_score": round(min(s1, s2), 3),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }))

        result = [d for idx, d in enumerate(detections) if idx not in discard]
        if discard:
            logger.info(json.dumps({
                "event": "fusion_complete",
                "input_detections": n,
                "output_detections": len(result),
                "resolved_conflicts": len(discard),
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
        return result

    def _fusion_score(self, det: object, track_map: dict) -> float:
        """
        Compute the fusion score for one detection.

        formula: W_conf*confidence + W_ctx*context + W_hist*history
        """
        confidence = det.confidence

        matching_tracks = track_map.get(det.class_name, [])
        if matching_tracks:
            best_stability = max(t.stability_score for t in matching_tracks)
            # Context baseline 0.5 scales to 1.0 as the class becomes established
            context = 0.5 + 0.5 * best_stability
            history = best_stability
        else:
            context = 0.5   # no corroborating history
            history = 0.0

        return round(
            min(1.0, _W_CONFIDENCE * confidence
                     + _W_CONTEXT   * context
                     + _W_HISTORY   * history),
            3,
        )

    @staticmethod
    def _build_track_map(tracks: list) -> dict[str, list]:
        track_map: dict[str, list] = {}
        for t in tracks:
            track_map.setdefault(t.class_name, []).append(t)
        return track_map
