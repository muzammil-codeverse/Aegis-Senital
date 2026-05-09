"""
WatchlistStore — thread-safe append-only watchlist with TTL/expiry support.

Persistence strategy:
- watchlist.jsonl — one entry per line; atomically rewritten on deactivation

Design notes:
- Entries are never deleted from disk; deactivating sets active=False.
- expire_stale() must be called periodically to deactivate TTL-expired entries.
- get_max_severity_for_identity() enables fast severity lookups for alert routing.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Resolve project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.models.identity_models import WatchlistEntry, WatchlistSeverity


class WatchlistStore:
    """Thread-safe append-only watchlist with TTL/expiry support."""

    MAX_ENTRIES = 10_000

    def __init__(self, store_dir: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        if store_dir is None:
            base = Path(__file__).resolve().parent.parent.parent
            store_dir = str(base / "storage" / "watchlists")
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._entries: Dict[str, WatchlistEntry] = {}       # watchlist_id -> entry
        self._by_identity: Dict[str, List[str]] = {}        # identity_id -> [watchlist_ids]
        self._load()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _watchlist_path(self) -> Path:
        return self._store_dir / "watchlist.jsonl"

    # ------------------------------------------------------------------
    # Bootstrap persistence load
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            if not self._watchlist_path().exists():
                return
            with open(self._watchlist_path(), "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        entry = WatchlistEntry.from_dict(d)
                        self._entries[entry.watchlist_id] = entry
                        if entry.identity_id not in self._by_identity:
                            self._by_identity[entry.identity_id] = []
                        if entry.watchlist_id not in self._by_identity[entry.identity_id]:
                            self._by_identity[entry.identity_id].append(entry.watchlist_id)
                    except Exception as exc:
                        logger.warning("Failed to load watchlist entry: %s", exc)
            logger.info("WatchlistStore loaded %d entries", len(self._entries))

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _append_jsonl(self, data: dict) -> None:
        with open(self._watchlist_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(data) + "\n")

    def _rewrite(self) -> None:
        """Atomically rewrite watchlist JSONL after status changes."""
        tmp = self._watchlist_path().with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for entry in self._entries.values():
                fh.write(json.dumps(entry.to_dict()) + "\n")
        tmp.replace(self._watchlist_path())

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def add_to_watchlist(
        self,
        identity_id: str,
        severity: str = WatchlistSeverity.MEDIUM,
        reason: Optional[str] = None,
        expires_at: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> WatchlistEntry:
        with self._lock:
            entry = WatchlistEntry(
                identity_id=identity_id,
                severity=severity,
                reason=reason,
                expires_at=expires_at,
                metadata=metadata or {},
            )
            self._entries[entry.watchlist_id] = entry
            if identity_id not in self._by_identity:
                self._by_identity[identity_id] = []
            self._by_identity[identity_id].append(entry.watchlist_id)
            self._append_jsonl(entry.to_dict())
            return entry

    def remove_from_watchlist(self, watchlist_id: str) -> bool:
        """Deactivate an entry (sets active=False and rewrites disk)."""
        with self._lock:
            if watchlist_id not in self._entries:
                return False
            self._entries[watchlist_id].active = False
            self._rewrite()
            return True

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_watchlist_entry(self, watchlist_id: str) -> Optional[WatchlistEntry]:
        with self._lock:
            return self._entries.get(watchlist_id)

    def list_watchlist(
        self,
        active: bool = True,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[WatchlistEntry]:
        with self._lock:
            now = time.time()
            results = []
            for entry in self._entries.values():
                if active and not entry.active:
                    continue
                if active and entry.expires_at and entry.expires_at < now:
                    continue
                if severity and entry.severity != severity:
                    continue
                results.append(entry)
            return results[:limit]

    def is_watchlisted(self, identity_id: str) -> bool:
        """Return True if the identity has at least one active, non-expired entry."""
        with self._lock:
            now = time.time()
            for wid in self._by_identity.get(identity_id, []):
                entry = self._entries.get(wid)
                if entry and entry.active:
                    if entry.expires_at is None or entry.expires_at > now:
                        return True
            return False

    def get_identity_watchlist(self, identity_id: str) -> List[WatchlistEntry]:
        """Return all watchlist entries (any state) for an identity."""
        with self._lock:
            results = []
            for wid in self._by_identity.get(identity_id, []):
                entry = self._entries.get(wid)
                if entry:
                    results.append(entry)
            return results

    def expire_stale(self, now: Optional[float] = None) -> int:
        """
        Mark expired entries as inactive.

        Returns the number of entries newly deactivated.
        """
        if now is None:
            now = time.time()
        with self._lock:
            count = 0
            changed = False
            for entry in self._entries.values():
                if entry.active and entry.expires_at and entry.expires_at < now:
                    entry.active = False
                    count += 1
                    changed = True
            if changed:
                self._rewrite()
            return count

    def get_max_severity_for_identity(self, identity_id: str) -> Optional[str]:
        """
        Return the highest active severity for an identity, or None if not watchlisted.

        Order: critical > high > medium > low.
        """
        severity_order: Dict[str, int] = {
            WatchlistSeverity.CRITICAL: 3,
            WatchlistSeverity.HIGH: 2,
            WatchlistSeverity.MEDIUM: 1,
            WatchlistSeverity.LOW: 0,
        }
        with self._lock:
            now = time.time()
            max_sev: Optional[str] = None
            max_order = -1
            for wid in self._by_identity.get(identity_id, []):
                entry = self._entries.get(wid)
                if entry and entry.active:
                    if entry.expires_at is None or entry.expires_at > now:
                        o = severity_order.get(entry.severity, 0)
                        if o > max_order:
                            max_order = o
                            max_sev = entry.severity
            return max_sev


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_watchlist_instance: Optional[WatchlistStore] = None
_watchlist_lock = threading.Lock()


def get_watchlist_store() -> WatchlistStore:
    """Return (or lazily create) the process-wide WatchlistStore singleton."""
    global _watchlist_instance
    with _watchlist_lock:
        if _watchlist_instance is None:
            _watchlist_instance = WatchlistStore()
        return _watchlist_instance
