import { useCallback, useEffect, useState } from 'react'
import { getGisConfig, getGisLayers } from '../api/gisApi'
import { normalizeError } from '../api/client'
import { useAuthGate } from './useAuthenticatedQuery'

export function useGisMap({ enabled = true, filters = {}, pollMs = 30_000 } = {}) {
  const gate = useAuthGate('gis:read', { enabled })
  const [config, setConfig] = useState(null)
  const [layers, setLayers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refreshConfig = useCallback(async () => {
    if (!gate.enabled) {
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      return
    }
    try {
      const res = await getGisConfig()
      setConfig(res.item)
    } catch (e) {
      setError(normalizeError(e))
    }
  }, [gate.enabled, gate.message, gate.reason])

  const refreshLayers = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setLayers(null)
      return
    }
    setLoading(true)
    try {
      const res = await getGisLayers(filters)
      setLayers(res.item)
      setError(null)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }, [filters, gate.enabled, gate.message, gate.reason])

  useEffect(() => {
    refreshConfig()
  }, [refreshConfig])

  useEffect(() => {
    refreshLayers()
    if (!pollMs || !gate.enabled) return undefined
    const t = window.setInterval(refreshLayers, pollMs)
    return () => window.clearInterval(t)
  }, [gate.enabled, refreshLayers, pollMs])

  return { config, layers, loading, error, authGate: gate, refreshLayers, refreshConfig }
}
