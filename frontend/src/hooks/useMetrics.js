import { useCallback, useEffect, useRef, useState } from 'react'
import { getCoreMetrics } from '../api/metricsApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { runtimeStore } from '../state/runtimeStore'

export function useMetrics({ pollMs = DASHBOARD_POLL_MS } = {}) {
  const [metrics, setMetrics] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [stale, setStale] = useState(false)
  const hasDataRef = useRef(false)

  const refresh = useCallback(async () => {
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
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(timer)
  }, [pollMs, refresh])

  return { metrics, loading, error, stale, updatedAt, refresh }
}
