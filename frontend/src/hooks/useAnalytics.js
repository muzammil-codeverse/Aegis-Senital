import { startTransition, useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { subDays, subHours } from 'date-fns'
import {
  exportAnalytics,
  getAnomalyTrends,
  getCameraHeatmap,
  getCameraRisk,
  getCaseSummary,
  getCaseTimeseries,
  getDashboardOverview,
  getEventsByType,
  getEventTimeseries,
  getIdentitySummary,
  getModelPerformance,
  getOpenVocabSummary,
  getOperatorWorkload,
  getStreamReliability,
  getSystemPerformance,
} from '../api/analyticsApi'
import { normalizeError } from '../api/client'
import { useAuthGate } from './useAuthenticatedQuery'

const DEFAULT_FILTERS = {
  window: '24h',
  bucket: '1h',
  camera_id: '',
  severity: '',
  q: '',
}

function resolveWindowStart(windowKey, endAt) {
  if (windowKey === '6h') return subHours(endAt, 6)
  if (windowKey === '7d') return subDays(endAt, 7)
  if (windowKey === '30d') return subDays(endAt, 30)
  return subHours(endAt, 24)
}

function buildQuery(filters) {
  const end = new Date()
  const start = resolveWindowStart(filters.window, end)
  return {
    start: start.toISOString(),
    end: end.toISOString(),
    bucket: filters.bucket,
    camera_id: filters.camera_id || undefined,
    severity: filters.severity || undefined,
    q: filters.q || undefined,
  }
}

function buildExportPayload(filters, sections, format) {
  const query = buildQuery(filters)
  return {
    format,
    sections,
    time_range: {
      start: query.start,
      end: query.end,
      bucket: query.bucket,
    },
    filters: Object.fromEntries(
      Object.entries({
        camera_id: query.camera_id,
        severity: query.severity,
        q: query.q,
      }).filter(([, value]) => value !== undefined),
    ),
  }
}

export function useAnalytics({ enabled = true, pollMs = 30000, initialFilters = {} } = {}) {
  const gate = useAuthGate('analytics:read', { enabled })
  const [overview, setOverview] = useState(null)
  const [eventTimeseries, setEventTimeseries] = useState([])
  const [eventsByType, setEventsByType] = useState([])
  const [caseSummary, setCaseSummary] = useState(null)
  const [caseTimeseries, setCaseTimeseries] = useState([])
  const [cameraRisk, setCameraRisk] = useState([])
  const [cameraHeatmap, setCameraHeatmap] = useState([])
  const [modelPerformance, setModelPerformance] = useState([])
  const [anomalyTrends, setAnomalyTrends] = useState(null)
  const [identitySummary, setIdentitySummary] = useState(null)
  const [openVocabSummary, setOpenVocabSummary] = useState(null)
  const [streamReliability, setStreamReliability] = useState([])
  const [operatorWorkload, setOperatorWorkload] = useState([])
  const [systemPerformance, setSystemPerformance] = useState(null)
  const [loading, setLoading] = useState(Boolean(enabled))
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ ...DEFAULT_FILTERS, ...initialFilters })
  const [exporting, setExporting] = useState(false)
  const deferredFilters = useDeferredValue(filters)

  const query = useMemo(() => buildQuery(deferredFilters), [deferredFilters])

  const refresh = useCallback(async (overrideFilters = null) => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      return
    }
    const activeFilters = overrideFilters ? { ...filters, ...overrideFilters } : deferredFilters
    const activeQuery = buildQuery(activeFilters)
    setLoading(true)
    const results = await Promise.allSettled([
      getDashboardOverview(activeQuery),
      getEventTimeseries(activeQuery),
      getEventsByType(activeQuery),
      getCaseSummary(activeQuery),
      getCaseTimeseries(activeQuery),
      getCameraRisk(activeQuery),
      getCameraHeatmap(activeQuery),
      getModelPerformance(activeQuery),
      getAnomalyTrends(activeQuery),
      getIdentitySummary(activeQuery),
      getOpenVocabSummary(activeQuery),
      getStreamReliability(activeQuery),
      getOperatorWorkload(activeQuery),
      getSystemPerformance(activeQuery),
    ])

    const firstError = results.find(result => result.status === 'rejected')
    startTransition(() => {
      if (!firstError) {
        setError(null)
      } else {
        setError(normalizeError(firstError.reason))
      }

      const readItem = index => (results[index].status === 'fulfilled' ? results[index].value.item : null)
      const readItems = index => (results[index].status === 'fulfilled' ? results[index].value.items : [])

      setOverview(readItem(0))
      setEventTimeseries(readItems(1))
      setEventsByType(readItems(2))
      setCaseSummary(readItem(3))
      setCaseTimeseries(readItems(4))
      setCameraRisk(readItems(5))
      setCameraHeatmap(readItems(6))
      setModelPerformance(readItems(7))
      setAnomalyTrends(readItem(8))
      setIdentitySummary(readItem(9))
      setOpenVocabSummary(readItem(10))
      setStreamReliability(readItems(11))
      setOperatorWorkload(readItems(12))
      setSystemPerformance(readItem(13))
      setLoading(false)
    })
  }, [deferredFilters, filters, gate.enabled, gate.message, gate.reason])

  const exportData = useCallback(async ({ sections, format }) => {
    setExporting(true)
    try {
      const response = await exportAnalytics(buildExportPayload(filters, sections, format))
      setError(null)
      return response.item
    } catch (err) {
      const message = normalizeError(err)
      setError(message)
      throw err
    } finally {
      setExporting(false)
    }
  }, [filters])

  useEffect(() => {
    const initialTimer = window.setTimeout(() => { refresh() }, 0)
    return () => window.clearTimeout(initialTimer)
  }, [query, refresh])

  useEffect(() => {
    if (!gate.enabled) return undefined
    const timer = window.setInterval(() => refresh(), pollMs)
    return () => window.clearInterval(timer)
  }, [gate.enabled, pollMs, refresh])

  return {
    overview,
    eventTimeseries,
    eventsByType,
    caseSummary,
    caseTimeseries,
    cameraRisk,
    cameraHeatmap,
    modelPerformance,
    anomalyTrends,
    identitySummary,
    openVocabSummary,
    streamReliability,
    operatorWorkload,
    systemPerformance,
    loading,
    error,
    filters,
    setFilters,
    refresh,
    exportData,
    exporting,
    authGate: gate,
  }
}
