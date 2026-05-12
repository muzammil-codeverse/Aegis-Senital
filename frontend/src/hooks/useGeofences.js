import { useCallback, useEffect, useState } from 'react'
import { getGeofences } from '../api/gisApi'
import { normalizeError } from '../api/client'

export function useGeofences({ enabled = true, pollMs = 60_000 } = {}) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    try {
      const res = await getGeofences()
      setItems(res.items)
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

  return { items, loading, error, refresh }
}
