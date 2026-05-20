import { useCallback, useEffect, useState } from 'react';
import { anomalyApi } from '../api/anomalyApi';
import { normalizeError } from '../api/client';
import { useAuthGate } from './useAuthenticatedQuery';

function anomalyItems(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.events)) return payload.events;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

export function useAnomalyEvents(cameraId = null, pollIntervalMs = 5000) {
  const gate = useAuthGate('alert:read');
  const [events, setEvents] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchEvents = useCallback(async () => {
    if (!gate.enabled) {
      setEvents([]);
      setError(gate.reason === 'checking' || gate.reason === 'disabled' ? null : gate.message);
      return [];
    }

    try {
      const payload = cameraId
        ? await anomalyApi.getCameraEvents(cameraId)
        : await anomalyApi.getRecentEvents({ limit: 50 });
      const nextEvents = anomalyItems(payload);
      setEvents(nextEvents);
      setError(null);
      return nextEvents;
    } catch (err) {
      setError(normalizeError(err));
      return [];
    }
  }, [cameraId, gate.enabled, gate.message, gate.reason]);

  const fetchHealth = useCallback(async () => {
    if (!gate.enabled) {
      setHealth(null);
      return null;
    }

    try {
      const payload = await anomalyApi.getHealth();
      setHealth(payload?.item || payload || null);
      return payload;
    } catch {
      // Health is advisory; anomaly events can still render if it is absent.
      setHealth(null);
      return null;
    }
  }, [gate.enabled]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(gate.reason === 'checking' || gate.enabled);
      await Promise.all([fetchEvents(), fetchHealth()]);
      if (!cancelled) setLoading(false);
    };

    load();
    if (!gate.enabled) {
      return () => {
        cancelled = true;
      };
    }

    const timer = setInterval(fetchEvents, pollIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [fetchEvents, fetchHealth, gate.enabled, gate.reason, pollIntervalMs]);

  const submitFeedback = useCallback(async (eventId, isFalseAlarm) => {
    if (!gate.enabled) {
      setError(gate.message);
      return;
    }

    try {
      await anomalyApi.submitFeedback(eventId, isFalseAlarm);
      await fetchEvents();
    } catch (err) {
      setError(normalizeError(err));
    }
  }, [fetchEvents, gate.enabled, gate.message]);

  return { events, health, loading, error, refetch: fetchEvents, submitFeedback, authGate: gate };
}
