import { useState, useEffect, useCallback } from 'react'
import {
  getOpenVocabStatus,
  getOpenVocabPrompts,
  createOpenVocabPrompt,
  updateOpenVocabPrompt,
  disableOpenVocabPrompt,
  scanLatestFrame,
  scanIncident,
  scanImage,
  getOpenVocabResults,
  loadOpenVocabModel,
  unloadOpenVocabModel,
  reloadOpenVocabModel,
  getOpenVocabModelStatus,
} from '../api/openVocabApi'
import { useOpenVocabStream } from './useOpenVocabStream'

/**
 * Hook for managing open-vocabulary threat scanner state.
 * Phase 25: adds WebSocket streaming with polling fallback.
 * Provides status, prompt library, results, scan actions, model control,
 * and live per-camera threat badges.
 */
export function useOpenVocab() {
  const [status, setStatus] = useState(null)
  const [prompts, setPrompts] = useState([])
  const [results, setResults] = useState([])
  const [modelStatus, setModelStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [unavailable, setUnavailable] = useState(false)

  // Phase 25 — live WebSocket stream
  const {
    connected: wsConnected,
    transport: wsTransport,
    lastResult: wsLastResult,
    streamError: wsError,
    cameraState: wsCameraState,
    getCameraEntry,
  } = useOpenVocabStream({ enabled: true })

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusRes, promptsRes, resultsRes, modelStatusRes] = await Promise.allSettled([
        getOpenVocabStatus(),
        getOpenVocabPrompts(),
        getOpenVocabResults(),
        getOpenVocabModelStatus(),
      ])
      if (statusRes.status === 'fulfilled') {
        const s = statusRes.value
        setStatus(s)
        const adapterAvailable = s?.item?.adapter?.available
        setUnavailable(s?.status === 'unavailable' || adapterAvailable === false)
      }
      if (promptsRes.status === 'fulfilled') {
        setPrompts(promptsRes.value?.items || [])
      }
      if (resultsRes.status === 'fulfilled') {
        setResults(resultsRes.value?.items || [])
      }
      if (modelStatusRes.status === 'fulfilled') {
        setModelStatus(modelStatusRes.value?.adapter || null)
      }
    } catch (e) {
      setError(e?.message || 'Failed to load open-vocab data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const triggerScanLatestFrame = useCallback(async (cameraId, promptsList) => {
    try {
      const res = await scanLatestFrame(cameraId, promptsList)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Scan failed')
      return null
    }
  }, [refresh])

  const triggerScanIncident = useCallback(async (incidentId, promptsList) => {
    try {
      const res = await scanIncident(incidentId, promptsList)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Scan failed')
      return null
    }
  }, [refresh])

  const triggerScanImage = useCallback(async (file, promptsList) => {
    try {
      const res = await scanImage(file, promptsList)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Image scan failed')
      return null
    }
  }, [refresh])

  const addPrompt = useCallback(async (payload) => {
    try {
      const res = await createOpenVocabPrompt(payload)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Failed to create prompt')
      return null
    }
  }, [refresh])

  const editPrompt = useCallback(async (promptId, payload) => {
    try {
      const res = await updateOpenVocabPrompt(promptId, payload)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Failed to update prompt')
      return null
    }
  }, [refresh])

  const removePrompt = useCallback(async (promptId) => {
    try {
      const res = await disableOpenVocabPrompt(promptId)
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Failed to disable prompt')
      return null
    }
  }, [refresh])

  /** Load the open-vocabulary model adapter via the hot-load API. */
  const loadModel = useCallback(async () => {
    try {
      const res = await loadOpenVocabModel()
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Model load failed')
      return null
    }
  }, [refresh])

  /** Unload the open-vocabulary model adapter. */
  const unloadModel = useCallback(async () => {
    try {
      const res = await unloadOpenVocabModel()
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Model unload failed')
      return null
    }
  }, [refresh])

  /** Reload (unload + re-load) the open-vocabulary model adapter. */
  const reloadModel = useCallback(async () => {
    try {
      const res = await reloadOpenVocabModel()
      await refresh()
      return res
    } catch (e) {
      setError(e?.message || 'Model reload failed')
      return null
    }
  }, [refresh])

  return {
    status,
    prompts,
    results,
    modelStatus,
    loading,
    error,
    unavailable,
    refresh,
    scanLatestFrame: triggerScanLatestFrame,
    scanIncident: triggerScanIncident,
    scanImage: triggerScanImage,
    createPrompt: addPrompt,
    updatePrompt: editPrompt,
    disablePrompt: removePrompt,
    loadModel,
    unloadModel,
    reloadModel,
    // Phase 25 — live streaming
    wsConnected,
    wsTransport,
    wsLastResult,
    wsError,
    wsCameraState,
    getCameraEntry,
  }
}
