import { useState, useEffect, useCallback, useRef } from 'react'
import { getActiveHandoffs, getRecentHandoffs } from '../api/handoffsApi'

const POLL_MS = 4000

export function useHandoffs({ pollMs = POLL_MS } = {}) {
  const [activeHandoffs, setActiveHandoffs] = useState([])
  const [recentHandoffs, setRecentHandoffs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const fetch = useCallback(async () => {
    try {
      const [active, recent] = await Promise.all([
        getActiveHandoffs(200),
        getRecentHandoffs(200),
      ])
      if (!mountedRef.current) return
      setActiveHandoffs(active)
      setRecentHandoffs(recent)
      setError(null)
    } catch (err) {
      if (mountedRef.current) setError(err?.message ?? 'Failed to load handoffs')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    fetch()
    const id = setInterval(fetch, pollMs)
    return () => {
      mountedRef.current = false
      clearInterval(id)
    }
  }, [fetch, pollMs])

  const mergeWebSocketHandoff = useCallback((wsHandoff) => {
    const id = wsHandoff?.handoff_id
    if (!id) return
    const state = wsHandoff?.state

    setActiveHandoffs((prev) => {
      const idx = prev.findIndex((h) => h.handoff_id === id)
      if (state === 'confirmed' || state === 'rejected' || state === 'expired') {
        return idx >= 0 ? prev.filter((h) => h.handoff_id !== id) : prev
      }
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...wsHandoff }
        return next
      }
      return [wsHandoff, ...prev]
    })

    setRecentHandoffs((prev) => {
      if (state !== 'confirmed' && state !== 'rejected' && state !== 'expired') return prev
      const idx = prev.findIndex((h) => h.handoff_id === id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...wsHandoff }
        return next
      }
      return [wsHandoff, ...prev.slice(0, 199)]
    })
  }, [])

  return { activeHandoffs, recentHandoffs, loading, error, refresh: fetch, mergeWebSocketHandoff }
}
