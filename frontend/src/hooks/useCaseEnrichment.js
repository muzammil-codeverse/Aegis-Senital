import { useCallback, useEffect, useState } from 'react'
import { normalizeError } from '../api/client'
import {
  addExternalLink,
  createSource,
  deleteSource,
  listSources,
  listSummaries,
  summarizeEnrichment,
  updateSource,
  uploadDocument,
} from '../api/osintApi'

export function useCaseEnrichment({ caseId, enabled = true, onChanged } = {}) {
  const [sources, setSources] = useState([])
  const [summaries, setSummaries] = useState([])
  const [loading, setLoading] = useState(Boolean(enabled && caseId))
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!enabled || !caseId) {
      setSources([])
      setSummaries([])
      setLoading(false)
      return { sources: [], summaries: [] }
    }
    setLoading(true)
    try {
      const [sourceResponse, summaryResponse] = await Promise.all([
        listSources(caseId),
        listSummaries(caseId),
      ])
      setSources(sourceResponse.items)
      setSummaries(summaryResponse.items)
      setError(null)
      return { sources: sourceResponse.items, summaries: summaryResponse.items }
    } catch (err) {
      setError(normalizeError(err))
      return { sources: [], summaries: [] }
    } finally {
      setLoading(false)
    }
  }, [caseId, enabled])

  useEffect(() => {
    refresh()
  }, [refresh])

  const applyAction = useCallback(async (fn) => {
    if (!caseId) return null
    setActionLoading(true)
    try {
      const item = await fn()
      await refresh()
      if (onChanged) await onChanged()
      setError(null)
      return item
    } catch (err) {
      setError(normalizeError(err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [caseId, onChanged, refresh])

  return {
    sources,
    summaries,
    loading,
    actionLoading,
    error,
    refresh,
    createSource: payload => applyAction(async () => (await createSource(caseId, payload)).item),
    addExternalLink: payload => applyAction(async () => (await addExternalLink(caseId, payload)).item),
    uploadDocument: (file, metadata) => applyAction(async () => (await uploadDocument(caseId, file, metadata)).item),
    updateSource: (sourceId, payload) => applyAction(async () => (await updateSource(caseId, sourceId, payload)).item),
    deleteSource: sourceId => applyAction(async () => (await deleteSource(caseId, sourceId)).item),
    summarize: payload => applyAction(async () => (await summarizeEnrichment(caseId, payload)).item),
  }
}
