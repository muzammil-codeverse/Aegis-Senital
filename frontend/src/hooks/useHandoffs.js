import { useState, useEffect, useCallback, useRef } from 'react'
import { getActiveHandoffs, getRecentHandoffs } from '../api/handoffsApi'
import { useAuthGate } from './useAuthenticatedQuery'

const POLL_MS = 4000

export function useHandoffs({ pollMs = POLL_MS, enabled = true } = {}) {
  const gate = useAuthGate('map:read', { enabled })
  const [activeHandoffs, setActiveHandoffs] = useState([])
  const [recentHandoffs, setRecentHandoffs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const fetch = useCallback(async () => {
    if (!gate.enabled) {
      if (!mountedRef.current) return
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setActiveHandoffs([])
      setRecentHandoffs([])
      return
    }
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
  }, [gate.enabled, gate.message, gate.reason])

  useEffect(() => {
    mountedRef.current = true
    const initialTimer = window.setTimeout(fetch, 0)
    if (!gate.enabled) {
      return () => {
        mountedRef.current = false
        window.clearTimeout(initialTimer)
      }
    }
    const id = setInterval(fetch, pollMs)
    return () => {
      mountedRef.current = false
      window.clearTimeout(initialTimer)
      clearInterval(id)
    }
  }, [fetch, gate.enabled, pollMs])

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

  return { activeHandoffs, recentHandoffs, loading, error, authGate: gate, refresh: fetch, mergeWebSocketHandoff }
}
