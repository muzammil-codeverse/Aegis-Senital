import { useCallback, useEffect, useRef, useState } from 'react'
import { getMapState } from '../api/mapApi'
import { normalizeError } from '../api/client'

const DEFAULT_POLL_MS = 10000

export function useMapState({ pollMs = DEFAULT_POLL_MS } = {}) {
  const [mapState, setMapState] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCameraId, setSelectedCameraId] = useState(null)
  const [selectedZoneId, setSelectedZoneId] = useState(null)
  const timerRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const state = await getMapState()
      setMapState(state)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    timerRef.current = setInterval(refresh, pollMs)
    return () => clearInterval(timerRef.current)
  }, [refresh, pollMs])

  return {
    mapState,
    loading,
    error,
    refresh,
    selectedCameraId,
    setSelectedCameraId,
    selectedZoneId,
    setSelectedZoneId,
  }
}
