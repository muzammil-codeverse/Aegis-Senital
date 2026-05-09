/**
 * useWatchlist — polling hook for active watchlist entries.
 *
 * Exposes add/remove mutations that auto-refresh on success.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getWatchlist,
  addWatchlistEntry,
  removeWatchlistEntry,
  getIdentityWatchlist,
} from '../api/identityApi.js';

const POLL_MS = 10000;

export function useWatchlist(pollInterval = POLL_MS) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await getWatchlist({ active: true });
      if (res.status !== 'error') {
        setEntries(res.items || []);
        setError(null);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWatchlist();
    timerRef.current = setInterval(fetchWatchlist, pollInterval);
    return () => clearInterval(timerRef.current);
  }, [fetchWatchlist, pollInterval]);

  const addEntry = useCallback(async (payload) => {
    const res = await addWatchlistEntry(payload);
    if (res.status === 'ok') await fetchWatchlist();
    return res;
  }, [fetchWatchlist]);

  const removeEntry = useCallback(async (watchlistId) => {
    const res = await removeWatchlistEntry(watchlistId);
    if (res.status === 'ok') await fetchWatchlist();
    return res;
  }, [fetchWatchlist]);

  const getForIdentity = useCallback(async (identityId) => {
    return await getIdentityWatchlist(identityId);
  }, []);

  return {
    entries,
    loading,
    error,
    refresh: fetchWatchlist,
    addEntry,
    removeEntry,
    getForIdentity,
  };
}
