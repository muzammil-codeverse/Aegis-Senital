import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getIncident, getIncidents } from '../api/incidentsApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { incidentStore } from '../state/incidentStore'
import { compareSeverity } from '../utils/severity'
import { useAuthGate } from './useAuthenticatedQuery'

export function useIncidents({ enabled = true, pollMs = DASHBOARD_POLL_MS, limit = 100 } = {}) {
  const gate = useAuthGate('incident:read', { enabled })
  const [incidents, setIncidents] = useState([])
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [stale, setStale] = useState(false)
  const hasDataRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setIncidents([])
      incidentStore.setIncidents([])
      return
    }
    try {
      const response = await getIncidents({ limit })
      setIncidents(response.items)
      incidentStore.setIncidents(response.items)
      setError(null)
      setStale(false)
      setUpdatedAt(Date.now())
      hasDataRef.current = true
    } catch (err) {
      setError(normalizeError(err))
      setStale(hasDataRef.current)
    } finally {
      setLoading(false)
    }
  }, [gate.enabled, gate.message, gate.reason, limit])

  const selectIncident = useCallback(async incidentId => {
    if (!incidentId) {
      setSelectedIncident(null)
      incidentStore.selectIncident(null)
      return
    }
    setDetailLoading(true)
    setDetailError(null)
    incidentStore.selectIncident(incidentId)
    try {
      const response = await getIncident(incidentId)
      setSelectedIncident(response.item)
      if (!response.item) setDetailError('Incident was not found')
    } catch (err) {
      setDetailError(normalizeError(err))
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialTimer = window.setTimeout(refresh, 0)
    if (!gate.enabled) {
      return () => window.clearTimeout(initialTimer)
    }
    const timer = window.setInterval(refresh, pollMs)
    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [gate.enabled, pollMs, refresh])

  const sortedIncidents = useMemo(() => (
    [...incidents].sort((a, b) => {
      const severityOrder = compareSeverity(a.severity, b.severity)
      if (severityOrder !== 0) return severityOrder
      return Number(b.updated_at || 0) - Number(a.updated_at || 0)
    })
  ), [incidents])

  return {
    incidents: sortedIncidents,
    selectedIncident,
    loading,
    detailLoading,
    error,
    detailError,
    stale,
    updatedAt,
    authGate: gate,
    refresh,
    selectIncident,
  }
}
