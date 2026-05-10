import { useState, useEffect, useCallback } from 'react';
import { anomalyApi } from '../api/anomalyApi';

export function useAnomalyEvents(cameraId = null, pollIntervalMs = 5000) {
  const [events, setEvents] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchEvents = useCallback(async () => {
    try {
      const res = cameraId
        ? await anomalyApi.getCameraEvents(cameraId)
        : await anomalyApi.getRecentEvents({ limit: 50 });
      setEvents(res.data?.events || res.data || []);
      setError(null);
    } catch (err) {
      setError(err?.message || 'Failed to fetch anomaly events');
    }
  }, [cameraId]);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await anomalyApi.getHealth();
      setHealth(res.data);
    } catch {
      // health endpoint may not exist yet — degrade silently
      setHealth(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchEvents(), fetchHealth()]);
      if (!cancelled) setLoading(false);
    };
    load();
    const timer = setInterval(fetchEvents, pollIntervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [fetchEvents, fetchHealth, pollIntervalMs]);

  const submitFeedback = useCallback(async (eventId, isFalseAlarm) => {
    try {
      await anomalyApi.submitFeedback(eventId, isFalseAlarm);
      await fetchEvents();
    } catch (err) {
      setError(err?.message || 'Feedback submission failed');
    }
  }, [fetchEvents]);

  return { events, health, loading, error, refetch: fetchEvents, submitFeedback };
}
