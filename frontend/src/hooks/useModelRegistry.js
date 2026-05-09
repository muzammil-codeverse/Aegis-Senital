/**
 * useModelRegistry — polling hook for the ML model registry.
 *
 * Exposes reload (force disk re-read) and per-model update operations.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { getModels, reloadModels, updateModel } from '../api/identityApi.js';

const POLL_MS = 15000;

export function useModelRegistry(pollInterval = POLL_MS) {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloading, setReloading] = useState(false);
  const timerRef = useRef(null);

  const fetchModels = useCallback(async () => {
    try {
      const res = await getModels();
      if (res.status !== 'error') {
        setModels(res.items || []);
        setError(null);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
    timerRef.current = setInterval(fetchModels, pollInterval);
    return () => clearInterval(timerRef.current);
  }, [fetchModels, pollInterval]);

  const reload = useCallback(async () => {
    setReloading(true);
    try {
      await reloadModels();
      await fetchModels();
    } finally {
      setReloading(false);
    }
  }, [fetchModels]);

  const update = useCallback(async (modelId, payload) => {
    const res = await updateModel(modelId, payload);
    if (res.status === 'ok') await fetchModels();
    return res;
  }, [fetchModels]);

  return {
    models,
    loading,
    error,
    reloading,
    refresh: fetchModels,
    reload,
    update,
  };
}
