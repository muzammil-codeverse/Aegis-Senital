import { useCallback, useEffect, useState } from 'react'
import { getCameraGeoProfile, getGisCameras, updateCameraGeoProfile } from '../api/gisApi'
import { normalizeError } from '../api/client'

export function useCameraGeoProfiles({ enabled = true, pollMs = 45_000 } = {}) {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!enabled) return
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
  }, [enabled])

  useEffect(() => {
    refresh()
    if (!pollMs) return undefined
    const t = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(t)
  }, [refresh, pollMs])

  const loadOne = useCallback(async cameraId => {
    const res = await getCameraGeoProfile(cameraId)
    return res.item
  }, [])

  const save = useCallback(async (cameraId, payload) => {
    await updateCameraGeoProfile(cameraId, payload)
    await refresh()
  }, [refresh])

  return { cameras, loading, error, refresh, loadOne, save }
}
