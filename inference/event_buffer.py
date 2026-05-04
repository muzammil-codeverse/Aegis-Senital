from __future__ import annotations
import json
import logging
from collections import deque
from datetime import datetime, timezone

from inference.schemas import FramePacket, Track, TrackTimeSeries

logger = logging.getLogger(__name__)

# ── noise suppression constants ────────────────────────────────────────────────
_NOISE_CONF_FLOOR = 0.20   # confidence below this for a brand-new track = noise


class EventBuffer:
    """
    Time-series event store and temporal context window.

    Dual internal store:
        _frames   – fixed-size FramePacket ring buffer (raw per-frame data)
        _series   – dict[track_id → TrackTimeSeries] (per-track time series)

    The series store only records confirmed detections (missed_frames == 0)
    so duration_frames reflects actual observation count, not projected frames.
    This is critical for the "no single-frame truth" contract: downstream
    engines check series.duration_frames before trusting any track.

    Three stream-processing features:
        noise suppression   – brand-new low-confidence tracks not added to series
        rolling aggregation – get_scene_density(), get_threat_summary()
        series pruning      – stale series (track not seen recently) are removed

    New API:
        buffer.add(frame_packet | list[Track])
        buffer.get_recent(n)              → list[FramePacket]
        buffer.get_track_history(tid)     → list[Track]   (legacy compatible)
        buffer.get_track_series(tid)      → TrackTimeSeries | None
        buffer.get_scene_density()        → float 0–1
        buffer.get_threat_summary()       → dict

    Legacy API (preserved for video_service.py):
        buffer.push(frame_events)
        buffer.confirmed_events(frame_events)
    """

    def __init__(
        self,
        maxlen: int = 60,
        window: int = 10,
        min_consecutive: int = 3,
    ) -> None:
        self._frames: deque[FramePacket] = deque(maxlen=maxlen)
        self._series: dict[int, TrackTimeSeries] = {}
        # Legacy confirmation window
        self._legacy_history: deque[frozenset] = deque(maxlen=window)
        self._min_consecutive = min_consecutive
        self._maxlen = maxlen

    # ── primary interface ──────────────────────────────────────────────────────

    def add(self, frame_data: FramePacket | list) -> None:
        """
        Ingest a FramePacket (or a bare list[Track]) into the buffer.

        Accepts list[Track] to support the section-9 shorthand:
            buffer.add(tracker.update(packet))
        In that case a minimal FramePacket is created from the tracks.
        """
        if isinstance(frame_data, FramePacket):
            packet = frame_data
        elif isinstance(frame_data, list):
            fid = frame_data[0].last_seen_frame if frame_data else 0
            camera_id = frame_data[0].camera_id if frame_data else "default"
            packet = FramePacket(frame_id=fid, detections=[], tracks=list(frame_data), camera_id=camera_id)
        else:
            raise TypeError(
                f"EventBuffer.add() expects FramePacket or list[Track], got {type(frame_data)}"
            )

        self._frames.append(packet)
        self._update_series(packet)

        logger.debug(json.dumps({
            "event": "buffer_add",
            "frame_id": packet.frame_id,
            "buffer_size": len(self._frames),
            "active_series": len(self._series),
            "ts": datetime.now(timezone.utc).isoformat(),
        }))

    def _update_series(self, packet: FramePacket) -> None:
        """
        Update the per-track time-series store for every confirmed track.

        Only tracks with missed_frames == 0 are written into the series
        (projected/predicted positions are skipped).  This ensures that
        series.duration_frames counts real detections only.
        """
        for track in packet.tracks:
            # Skip projected tracks (tracker filled in a predicted position)
            if track.missed_frames > 0:
                continue

            # Noise suppression: ignore brand-new tracks with very low confidence
            existing = self._series.get(track.track_id)
            is_noise = (
                existing is None
                and track.confidence < _NOISE_CONF_FLOOR
            )
            if is_noise:
                continue

            ts = self._series.setdefault(
                track.track_id,
                TrackTimeSeries(
                    track_id=track.track_id,
                    class_name=track.class_name,
                ),
            )
            ts.append(
                bbox=track.bbox,
                confidence=track.confidence,
                frame_id=packet.frame_id,
                threat_score=0.0,   # filled by event_engine on scoring pass
                camera_id=track.camera_id,
                identity_id=track.identity_id,
                identity_confidence=track.identity_confidence,
            )

        # Prune stale series: any track not seen in the last 2× buffer window
        if len(self._series) > self._maxlen * 2:
            live_tids: set[int] = {
                t.track_id
                for pkt in self._frames
                for t in pkt.tracks
            }
            for tid in [k for k in self._series if k not in live_tids]:
                del self._series[tid]

    # ── temporal queries ───────────────────────────────────────────────────────

    def get_recent(self, n_frames: int) -> list[FramePacket]:
        """Return the most recent n_frames packets, oldest-first."""
        if n_frames <= 0:
            return list(self._frames)
        return list(self._frames)[-n_frames:]

    def get_track_history(self, track_id: int) -> list[Track]:
        """
        Per-frame Track snapshots for track_id across all buffered frames.
        Preserved for backwards compatibility; prefer get_track_series() for
        richer statistics.
        """
        history: list[Track] = []
        for packet in self._frames:
            for track in packet.tracks:
                if track.track_id == track_id:
                    history.append(track)
                    break
        return history

    def get_track_series(self, track_id: int) -> TrackTimeSeries | None:
        """Return the full time-series for a track, or None if not seen."""
        return self._series.get(track_id)

    def get_scene_density(self, n_frames: int = 10) -> float:
        """
        Normalised scene busyness over recent frames.

        Returns 0.0–1.0 where 1.0 = 20+ active tracks per frame on average.
        Used by EventEngine to compute adaptive threat thresholds.
        """
        recent = self.get_recent(n_frames)
        if not recent:
            return 0.0
        avg_tracks = sum(len(p.tracks) for p in recent) / len(recent)
        return min(1.0, avg_tracks / 20.0)

    def get_threat_summary(self, n_frames: int = 30) -> dict:
        """Rolling statistics snapshot for telemetry."""
        recent = self.get_recent(n_frames)
        if not recent:
            return {}
        n = len(recent)
        return {
            "window_frames": n,
            "avg_detections_per_frame": round(
                sum(len(p.detections) for p in recent) / n, 2
            ),
            "avg_tracks_per_frame": round(
                sum(len(p.tracks) for p in recent) / n, 2
            ),
            "unique_series": len(self._series),
        }

    def __len__(self) -> int:
        return len(self._frames)

    # ── legacy interface (backwards compatibility) ─────────────────────────────

    def push(self, frame_events: list[dict]) -> None:
        """Legacy: record the event-type set seen this frame."""
        self._legacy_history.append(frozenset(e["event_type"] for e in frame_events))

    def confirmed_events(self, frame_events: list[dict]) -> list[dict]:
        """Legacy: return events confirmed in the last min_consecutive frames."""
        if len(self._legacy_history) < self._min_consecutive:
            return []
        recent = list(self._legacy_history)[-self._min_consecutive:]
        return [
            {**e, "confirmed": True}
            for e in frame_events
            if all(e["event_type"] in frame for frame in recent)
        ]
