import { useState, useCallback } from 'react';
import { investigationApi } from '../api/investigationApi';

export function useInvestigation() {
  const [hypotheses, setHypotheses] = useState([]);
  const [cameraGraph, setCameraGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reconstructing, setReconstructing] = useState(false);
  const [error, setError] = useState(null);

  const reconstructPath = useCallback(async (body) => {
    setReconstructing(true);
    setError(null);
    try {
      const data = await investigationApi.reconstructPath(body);
      const hyps = data?.item?.hypotheses || data?.hypotheses || [];
      setHypotheses((prev) => {
        const existingIds = new Set(prev.map((h) => h.hypothesis_id));
        const newOnes = hyps.filter((h) => !existingIds.has(h.hypothesis_id));
        return [...newOnes, ...prev];
      });
      return data;
    } catch (err) {
      setError(err?.message || 'Reconstruction failed');
      return null;
    } finally {
      setReconstructing(false);
    }
  }, []);

  const loadHypotheses = useCallback(async (params = {}) => {
    setLoading(true);
    setError(null);
    try {
      const data = await investigationApi.listHypotheses(params);
      setHypotheses(data?.items || []);
    } catch (err) {
      setError(err?.message || 'Failed to load hypotheses');
    } finally {
      setLoading(false);
    }
  }, []);

  const reviewHypothesis = useCallback(async (hypothesisId, action) => {
    try {
      let data;
      if (action === 'accept') data = await investigationApi.acceptHypothesis(hypothesisId);
      else if (action === 'reject') data = await investigationApi.rejectHypothesis(hypothesisId);
      else data = await investigationApi.markInconclusive(hypothesisId);
      const updated = data?.item;
      if (updated) {
        setHypotheses((prev) =>
          prev.map((h) => (h.hypothesis_id === hypothesisId ? updated : h))
        );
      }
      return data;
    } catch (err) {
      setError(err?.message || 'Review failed');
      return null;
    }
  }, []);

  const loadCameraGraph = useCallback(async () => {
    try {
      const data = await investigationApi.getCameraGraph();
      setCameraGraph(data?.item || null);
    } catch (err) {
      setError(err?.message || 'Failed to load camera graph');
    }
  }, []);

  return {
    hypotheses,
    cameraGraph,
    loading,
    reconstructing,
    error,
    reconstructPath,
    loadHypotheses,
    reviewHypothesis,
    loadCameraGraph,
  };
}
