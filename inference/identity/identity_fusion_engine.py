"""
IdentityFusionEngine — Phase 20 extension layer over GlobalIdentityRegistry.

Responsibilities:
- Record every identity match in the IdentityProfileStore.
- Check the WatchlistStore after each match.
- Publish WATCHLIST_HIT events when a watchlisted identity is matched above
  the configured confidence threshold (min_watchlist_confidence from
  identity_rules.yaml, default 0.72).

This module does NOT replace the existing GlobalIdentityRegistry or
TemporalIdentityGraph — it wraps them and adds persistence + alerting.

Thread safety: all state mutations delegate to thread-safe sub-systems.
No CUDA or GPU imports are performed at module load time.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration defaults (overridden by identity_rules.yaml)
_DEFAULT_MIN_WATCHLIST_CONFIDENCE = 0.72
_DEFAULT_MIN_IDENTITY_CONFIDENCE = 0.60


def _load_matching_config() -> dict:
    base = Path(__file__).resolve().parent.parent.parent
    cfg_path = base / "configs" / "runtime" / "identity_rules.yaml"
    if cfg_path.exists():
        try:
            import yaml  # type: ignore
            with open(cfg_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return data.get("matching", {})
        except Exception as exc:
            logger.warning("Could not load identity_rules.yaml matching config: %s", exc)
    return {}


class IdentityFusionEngine:
    """
    Wraps identity matching with persistence and watchlist alerting.

    Intended to be called after a successful face / appearance match in the
    inference pipeline.  Typical call site::

        engine = get_identity_fusion_engine()
        severity = engine.on_identity_matched(
            identity_id=identity_id,
            camera_id=camera_id,
            track_id=track_id,
            confidence=confidence,
        )
        if severity:
            # WATCHLIST_HIT event was already published; handle severity if needed
    """

    def __init__(self) -> None:
        cfg = _load_matching_config()
        self._min_watchlist_confidence: float = float(
            cfg.get("min_watchlist_confidence", _DEFAULT_MIN_WATCHLIST_CONFIDENCE)
        )
        self._min_identity_confidence: float = float(
            cfg.get("min_identity_confidence", _DEFAULT_MIN_IDENTITY_CONFIDENCE)
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_identity_matched(
        self,
        identity_id: str,
        camera_id: Optional[str] = None,
        track_id: Optional[int] = None,
        confidence: float = 0.0,
        source: str = "face",
        metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Called whenever an identity is matched in the inference pipeline.

        Records the match and, if above the watchlist confidence threshold,
        publishes a WATCHLIST_HIT event.

        Returns the watchlist severity string (e.g. "high") or None.
        """
        severity = self._check_watchlist_and_record(
            identity_id=identity_id,
            camera_id=camera_id,
            track_id=track_id,
            confidence=confidence,
            source=source,
            metadata=metadata or {},
        )
        return severity

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_watchlist_and_record(
        self,
        identity_id: str,
        camera_id: Optional[str],
        track_id: Optional[int],
        confidence: float,
        source: str = "face",
        metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """
        1. Record the match in the IdentityProfileStore.
        2. Check the WatchlistStore.
        3. If watchlisted and confidence >= threshold, publish WATCHLIST_HIT.

        Returns watchlist severity or None.
        """
        # Step 1 — record match
        try:
            from inference.identity.identity_profile_store import get_identity_store
            store = get_identity_store()
            store.record_match(
                identity_id=identity_id,
                camera_id=camera_id,
                track_id=track_id,
                confidence=confidence,
                source=source,
                metadata=metadata or {},
            )
            try:
                from inference.monitoring.metrics import get_metrics
                get_metrics().increment("identity_matches_recorded")
            except Exception:
                pass
        except Exception as exc:
            logger.warning("Failed to record identity match for %s: %s", identity_id, exc)

        # Step 2 — watchlist check (only above min confidence)
        if confidence < self._min_watchlist_confidence:
            return None

        severity: Optional[str] = None
        try:
            from inference.identity.watchlist_store import get_watchlist_store
            wl_store = get_watchlist_store()
            if wl_store.is_watchlisted(identity_id):
                severity = wl_store.get_max_severity_for_identity(identity_id)
        except Exception as exc:
            logger.warning(
                "Watchlist check failed for identity %s: %s", identity_id, exc
            )
            return None

        if severity is None:
            return None

        # Step 3 — publish WATCHLIST_HIT event
        self._publish_watchlist_hit(
            identity_id=identity_id,
            camera_id=camera_id,
            track_id=track_id,
            confidence=confidence,
            severity=severity,
            metadata=metadata or {},
        )
        return severity

    def _publish_watchlist_hit(
        self,
        identity_id: str,
        camera_id: Optional[str],
        track_id: Optional[int],
        confidence: float,
        severity: str,
        metadata: dict,
    ) -> None:
        """Publish a WATCHLIST_HIT event on the global EventBus."""
        try:
            from core.event_bus import get_event_bus
            from core.event_bus.event_types import EventType
            from inference.monitoring.metrics import get_metrics

            payload = {
                "event_type": "watchlist_hit",
                "identity_id": identity_id,
                "camera_id": camera_id,
                "camera_ids": [camera_id] if camera_id else [],
                "track_id": track_id,
                "track_ids": [track_id] if track_id is not None else [],
                "confidence": confidence,
                "severity": severity,
                "timestamp": time.time(),
                "metadata": metadata,
            }
            get_event_bus().publish(
                EventType.WATCHLIST_HIT,
                payload,
                source="identity_fusion_engine",
                priority=1 if severity == "critical" else 3,
            )
            try:
                get_metrics().increment("watchlist_hits")
            except Exception:
                pass
            logger.info(
                "WATCHLIST_HIT: identity=%s camera=%s confidence=%.2f severity=%s",
                identity_id,
                camera_id,
                confidence,
                severity,
            )
        except Exception as exc:
            logger.warning("Failed to publish WATCHLIST_HIT event: %s", exc)


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_fusion_instance: Optional[IdentityFusionEngine] = None
_fusion_lock = __import__("threading").Lock()


def get_identity_fusion_engine() -> IdentityFusionEngine:
    """Return (or lazily create) the process-wide IdentityFusionEngine singleton."""
    global _fusion_instance
    with _fusion_lock:
        if _fusion_instance is None:
            _fusion_instance = IdentityFusionEngine()
        return _fusion_instance
