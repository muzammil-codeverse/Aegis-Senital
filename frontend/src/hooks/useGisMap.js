import { useCallback, useEffect, useState } from 'react'
import { getGisConfig, getGisLayers } from '../api/gisApi'
import { normalizeError } from '../api/client'

export function useGisMap({ enabled = true, filters = {}, pollMs = 30_000 } = {}) {
  const [config, setConfig] = useState(null)
  const [layers, setLayers] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refreshConfig = useCallback(async () => {
    if (!enabled) return
    try {
      const res = await getGisConfig()
      setConfig(res.item)
    } catch (e) {
      setError(normalizeError(e))
    }
  }, [enabled])

  const refreshLayers = useCallback(async () => {
    if (!enabled) return
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
  }, [enabled, filters])

  useEffect(() => {
    refreshConfig()
  }, [refreshConfig])

  useEffect(() => {
    refreshLayers()
    if (!pollMs) return undefined
    const t = window.setInterval(refreshLayers, pollMs)
    return () => window.clearInterval(t)
  }, [refreshLayers, pollMs])

  return { config, layers, loading, error, refreshLayers, refreshConfig }
}
