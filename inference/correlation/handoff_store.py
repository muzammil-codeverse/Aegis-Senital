from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ACTIVE = 500
_DEFAULT_TTL = 120.0
_DEFAULT_RECENT_RETENTION = 1800.0


def _load_config() -> dict:
    try:
        from inference.config_runtime import load_runtime_config
        return load_runtime_config("handoff_rules")
    except Exception:
        return {}


class HandoffStore:
    """
    Thread-safe, bounded, TTL-aware store for handoff predictions and events.

    Maintains three indexes:
      _active   — predictions in PREDICTED / CANDIDATE state
      _recent   — completed (CONFIRMED / REJECTED / EXPIRED) within retention window
      _by_*     — secondary indexes by camera and identity
    """

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or _load_config()
        pred_cfg = cfg.get("prediction", {})
        exp_cfg = cfg.get("expiry", {})
        pers_cfg = cfg.get("persistence", {})

        self._max_active = int(pred_cfg.get("max_active_predictions", _DEFAULT_MAX_ACTIVE))
        self._ttl = float(pred_cfg.get("prediction_ttl_seconds", _DEFAULT_TTL))
        self._recent_retention = float(exp_cfg.get("recent_retention_seconds", _DEFAULT_RECENT_RETENTION))

        persist = bool(pers_cfg.get("enabled", True))
        base_dir_raw = pers_cfg.get("base_dir", "storage/handoffs")
        self._persist_dir: Path | None = None
        if persist:
            try:
                self._persist_dir = Path(base_dir_raw)
                self._persist_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                logger.warning("HandoffStore: persistence disabled: %s", exc)
                self._persist_dir = None

        self._lock = threading.RLock()
        # Primary stores
        self._active: dict[str, dict] = {}          # id → prediction
        self._recent: deque[dict] = deque(maxlen=2000)
        # Secondary indexes
        self._by_source: dict[str, set[str]] = defaultdict(set)
        self._by_target: dict[str, set[str]] = defaultdict(set)
        self._by_identity: dict[str, set[str]] = defaultdict(set)

    # ── write operations ──────────────────────────────────────────────────────

    def add_prediction(self, prediction: dict) -> None:
        hid = prediction.get("handoff_id", "")
        if not hid:
            return
        with self._lock:
            if len(self._active) >= self._max_active:
                self._evict_oldest_locked()
            self._active[hid] = prediction
            self._index_locked(hid, prediction)
        self._persist(prediction)
        self._inc_metric("handoff_predictions_created")

    def add_candidate(self, candidate: dict) -> None:
        hid = candidate.get("handoff_id", "")
        if not hid:
            return
        with self._lock:
            if hid in self._active:
                self._active[hid] = {**self._active[hid], **candidate}
            else:
                self._active[hid] = candidate
                self._index_locked(hid, candidate)
        self._persist(candidate)
        self._inc_metric("handoff_candidates_observed")

    def confirm_handoff(
        self,
        handoff_id: str,
        target_track_id: int | None = None,
        identity_id: str | None = None,
        confirmed_at: float | None = None,
    ) -> dict | None:
        with self._lock:
            pred = self._active.pop(handoff_id, None)
            if pred is None:
                return None
            pred["state"] = "confirmed"
            pred["confirmed_at"] = confirmed_at or time.time()
            if target_track_id is not None:
                pred["target_track_id"] = target_track_id
            if identity_id is not None:
                pred["identity_id"] = identity_id
            self._recent.append(pred)
            self._unindex_locked(handoff_id)
        self._persist(pred)
        self._inc_metric("handoffs_confirmed")
        return pred

    def reject_handoff(self, handoff_id: str, reason: str | None = None) -> dict | None:
        with self._lock:
            pred = self._active.pop(handoff_id, None)
            if pred is None:
                return None
            pred["state"] = "rejected"
            if reason:
                pred["reason"] = reason
            self._recent.append(pred)
            self._unindex_locked(handoff_id)
        self._persist(pred)
        self._inc_metric("handoffs_rejected")
        return pred

    def expire_stale(self, now: float | None = None) -> int:
        now = now or time.time()
        expired_ids = []
        with self._lock:
            for hid, pred in list(self._active.items()):
                if float(pred.get("expires_at", 0)) < now:
                    expired_ids.append(hid)
            for hid in expired_ids:
                pred = self._active.pop(hid)
                pred["state"] = "expired"
                self._recent.append(pred)
                self._unindex_locked(hid)

        # Also trim recent beyond retention
        cutoff = now - self._recent_retention
        with self._lock:
            while self._recent and float(self._recent[0].get("predicted_at", 0)) < cutoff:
                self._recent.popleft()

        for pred in [p for p in list(self._recent) if p.get("state") == "expired"]:
            self._persist(pred)
        self._inc_metric_n("handoffs_expired", len(expired_ids))
        return len(expired_ids)

    # ── read operations ───────────────────────────────────────────────────────

    def get_handoff(self, handoff_id: str) -> dict | None:
        with self._lock:
            pred = self._active.get(handoff_id)
            if pred:
                return dict(pred)
            for r in reversed(self._recent):
                if r.get("handoff_id") == handoff_id:
                    return dict(r)
        return None

    def list_active(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._active.values())
        items.sort(key=lambda p: p.get("predicted_at", 0), reverse=True)
        return items[:limit]

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._recent)
        items.sort(key=lambda p: p.get("predicted_at", 0), reverse=True)
        return items[:limit]

    def list_by_identity(self, identity_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            ids = set(self._by_identity.get(identity_id, set()))
            active = [dict(self._active[hid]) for hid in ids if hid in self._active]
            recent = [r for r in self._recent if r.get("identity_id") == identity_id]
        combined = active + recent
        combined.sort(key=lambda p: p.get("predicted_at", 0), reverse=True)
        seen: set[str] = set()
        result = []
        for p in combined:
            hid = p.get("handoff_id", "")
            if hid not in seen:
                seen.add(hid)
                result.append(p)
        return result[:limit]

    def list_by_camera(self, camera_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            src_ids = set(self._by_source.get(camera_id, set()))
            tgt_ids = set(self._by_target.get(camera_id, set()))
            ids = src_ids | tgt_ids
            active = [dict(self._active[hid]) for hid in ids if hid in self._active]
            recent = [
                r for r in self._recent
                if r.get("source_camera") == camera_id or r.get("target_camera") == camera_id
            ]
        combined = active + recent
        combined.sort(key=lambda p: p.get("predicted_at", 0), reverse=True)
        seen: set[str] = set()
        result = []
        for p in combined:
            hid = p.get("handoff_id", "")
            if hid not in seen:
                seen.add(hid)
                result.append(p)
        return result[:limit]

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    # ── private helpers ───────────────────────────────────────────────────────

    def _index_locked(self, hid: str, pred: dict) -> None:
        src = pred.get("source_camera", "")
        tgt = pred.get("target_camera", "")
        iid = pred.get("identity_id")
        if src:
            self._by_source[src].add(hid)
        if tgt:
            self._by_target[tgt].add(hid)
        if iid:
            self._by_identity[iid].add(hid)

    def _unindex_locked(self, hid: str) -> None:
        for index in (self._by_source, self._by_target, self._by_identity):
            for key in list(index.keys()):
                index[key].discard(hid)

    def _evict_oldest_locked(self) -> None:
        if not self._active:
            return
        oldest_id = min(self._active, key=lambda hid: self._active[hid].get("predicted_at", 0))
        pred = self._active.pop(oldest_id)
        pred["state"] = "expired"
        self._recent.append(pred)
        self._unindex_locked(oldest_id)

    def _persist(self, pred: dict) -> None:
        if not self._persist_dir:
            return
        try:
            import datetime
            ts = float(pred.get("predicted_at", time.time()))
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            path = self._persist_dir / dt.strftime("%Y/%m/%d/handoffs_%H.jsonl")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(pred, sort_keys=True) + "\n")
        except Exception as exc:
            logger.debug("HandoffStore persist failed: %s", exc)

    @staticmethod
    def _inc_metric(name: str) -> None:
        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment(name)
        except Exception:
            pass

    @staticmethod
    def _inc_metric_n(name: str, n: int) -> None:
        if n <= 0:
            return
        try:
            from inference.metrics import metrics as core_metrics
            core_metrics.increment(name, n)
        except Exception:
            pass
