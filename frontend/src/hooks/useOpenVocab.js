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
} from '../api/openVocabApi'

/**
 * Hook for managing open-vocabulary threat scanner state.
 * Provides status, prompt library, results, and scan actions.
 */
export function useOpenVocab() {
  const [status, setStatus] = useState(null)
  const [prompts, setPrompts] = useState([])
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [unavailable, setUnavailable] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusRes, promptsRes, resultsRes] = await Promise.allSettled([
        getOpenVocabStatus(),
        getOpenVocabPrompts(),
        getOpenVocabResults(),
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

  return {
    status,
    prompts,
    results,
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
  }
}
