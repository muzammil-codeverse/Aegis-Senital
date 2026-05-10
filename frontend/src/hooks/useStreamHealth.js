import { useCallback, useEffect, useState } from 'react'
import { normalizeError } from '../api/client'
import { getStreamHealth, getStreamStats } from '../api/streamingApi'

export function useStreamHealth(cameraId, { pollMs = 5000, enabled = true } = {}) {
  const [health, setHealth] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(Boolean(enabled && cameraId))
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!enabled || !cameraId) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [healthResponse, statsResponse] = await Promise.all([
        getStreamHealth(cameraId),
        getStreamStats(cameraId),
      ])
      setHealth(healthResponse.item)
      setStats(statsResponse.item)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [cameraId, enabled])

  useEffect(() => {
    refresh()
    if (!enabled || !cameraId) return undefined
    const timer = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(timer)
  }, [cameraId, enabled, pollMs, refresh])

  return { health, stats, loading, error, refresh }
}
