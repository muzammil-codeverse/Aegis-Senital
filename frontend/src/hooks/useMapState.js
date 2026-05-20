import { useCallback, useEffect, useRef, useState } from 'react'
import { getMapState } from '../api/mapApi'
import { normalizeError } from '../api/client'
import { useAuthGate } from './useAuthenticatedQuery'

const DEFAULT_POLL_MS = 10000

export function useMapState({ pollMs = DEFAULT_POLL_MS, enabled = true } = {}) {
  const gate = useAuthGate('map:read', { enabled })
  const [mapState, setMapState] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCameraId, setSelectedCameraId] = useState(null)
  const [selectedZoneId, setSelectedZoneId] = useState(null)
  const timerRef = useRef(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setMapState(null)
      return null
    }
    try {
      const state = await getMapState()
      setMapState(state)
      setError(null)
      return state
    } catch (err) {
      setError(normalizeError(err))
      return null
    } finally {
      setLoading(false)
    }
  }, [gate.enabled, gate.message, gate.reason])

  useEffect(() => {
    const initialTimer = window.setTimeout(refresh, 0)
    if (!gate.enabled) {
      return () => window.clearTimeout(initialTimer)
    }
    timerRef.current = setInterval(refresh, pollMs)
    return () => {
      window.clearTimeout(initialTimer)
      clearInterval(timerRef.current)
    }
  }, [gate.enabled, refresh, pollMs])

  return {
    mapState,
    loading,
    error,
    authGate: gate,
    refresh,
    selectedCameraId,
    setSelectedCameraId,
    selectedZoneId,
    setSelectedZoneId,
  }
}
