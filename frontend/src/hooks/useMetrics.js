import { useCallback, useEffect, useRef, useState } from 'react'
import { getCoreMetrics } from '../api/metricsApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { runtimeStore } from '../state/runtimeStore'
import { useAuthGate } from './useAuthenticatedQuery'

export function useMetrics({ enabled = true, pollMs = DASHBOARD_POLL_MS } = {}) {
  const gate = useAuthGate('metrics:read', { enabled })
  const [metrics, setMetrics] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [stale, setStale] = useState(false)
  const hasDataRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setMetrics({})
      return
    }
    try {
      const payload = await getCoreMetrics()
      setMetrics(payload)
      runtimeStore.setMetrics(payload)
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
  }, [gate.enabled, gate.message, gate.reason])

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

  return { metrics, loading, error, stale, updatedAt, authGate: gate, refresh }
}
