import { useCallback, useEffect, useState } from 'react'
import { getLatestFrames } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'

export function useLatestFrames({ pollMs = DASHBOARD_POLL_MS } = {}) {
  const [framesByCameraId, setFramesByCameraId] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const response = await getLatestFrames()
      const byId = {}
      for (const frame of response.items) {
        if (frame?.camera_id) byId[frame.camera_id] = frame
      }
      setFramesByCameraId(byId)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(timer)
  }, [pollMs, refresh])

  return {
    framesByCameraId,
    refresh,
    loading,
    error,
  }
}
