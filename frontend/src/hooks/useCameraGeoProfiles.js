import { useCallback, useEffect, useState } from 'react'
import { getCameraGeoProfile, getGisCameras, updateCameraGeoProfile } from '../api/gisApi'
import { normalizeError } from '../api/client'
import { useAuthGate } from './useAuthenticatedQuery'

export function useCameraGeoProfiles({ enabled = true, pollMs = 45_000 } = {}) {
  const gate = useAuthGate('gis:read', { enabled })
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setCameras([])
      return
    }
    setLoading(true)
    try {
      const res = await getGisCameras()
      setCameras(res.items)
      setError(null)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }, [gate.enabled, gate.message, gate.reason])

  useEffect(() => {
    refresh()
    if (!pollMs || !gate.enabled) return undefined
    const t = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(t)
  }, [gate.enabled, refresh, pollMs])

  const loadOne = useCallback(async cameraId => {
    const res = await getCameraGeoProfile(cameraId)
    return res.item
  }, [])

  const save = useCallback(async (cameraId, payload) => {
    await updateCameraGeoProfile(cameraId, payload)
    await refresh()
  }, [refresh])

  return { cameras, loading, error, authGate: gate, refresh, loadOne, save }
}
