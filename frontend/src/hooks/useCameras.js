import { useCallback, useEffect, useState } from 'react'
import { getCameras } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { useAuthGate } from './useAuthenticatedQuery'

export function useCameras({ pollMs = DASHBOARD_POLL_MS, enabled = true } = {}) {
  const gate = useAuthGate('camera:read', { enabled })
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCamera, setSelectedCamera] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setCameras([])
      return []
    }
    try {
      const response = await getCameras()
      setCameras(response.items)
      setError(null)
      return response.items
    } catch (err) {
      setError(normalizeError(err))
      return []
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
    cameras,
    loading,
    error,
    authGate: gate,
    refresh,
    selectedCamera,
    setSelectedCamera,
  }
}
