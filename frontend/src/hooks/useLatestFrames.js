import { useCallback, useEffect, useState } from 'react'
import { getLatestFrames } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { useAuthGate } from './useAuthenticatedQuery'

export function useLatestFrames({ pollMs = DASHBOARD_POLL_MS, enabled = true } = {}) {
  const gate = useAuthGate('camera:read', { enabled })
  const [framesByCameraId, setFramesByCameraId] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setFramesByCameraId({})
      return {}
    }
    try {
      const response = await getLatestFrames()
      const byId = {}
      for (const frame of response.items) {
        if (frame?.camera_id) byId[frame.camera_id] = frame
      }
      setFramesByCameraId(byId)
      setError(null)
      return byId
    } catch (err) {
      setError(normalizeError(err))
      return {}
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

  return {
    framesByCameraId,
    refresh,
    loading,
    error,
    authGate: gate,
  }
}
