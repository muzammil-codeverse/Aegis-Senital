import { useCallback, useEffect, useState } from 'react'
import { getCameras } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'

export function useCameras({ pollMs = DASHBOARD_POLL_MS } = {}) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCamera, setSelectedCamera] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const response = await getCameras()
      setCameras(response.items)
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
    cameras,
    loading,
    error,
    refresh,
    selectedCamera,
    setSelectedCamera,
  }
}
