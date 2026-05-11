import { useState, useEffect, useRef, useCallback } from 'react'
import { authUsesCookieMode, buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { useAuth } from './useAuth'

const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30000
const BACKOFF_FACTOR = 2
const MAX_HANDOFFS = 500

export function useWebSocketHandoffs() {
  const { token, authRequired } = useAuth()
  const [handoffs, setHandoffs] = useState({})
  const [status, setStatus] = useState('disconnected')
  const [lastMessageAt, setLastMessageAt] = useState(null)
  const [reconnectCount, setReconnectCount] = useState(0)
  const wsRef = useRef(null)
  const delayRef = useRef(BASE_DELAY_MS)
  const mountedRef = useRef(true)
  const retryRef = useRef(null)

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (authRequired && !token && !authUsesCookieMode()) {
      setStatus('auth_error')
      return
    }
    const url = buildWebSocketUrl('/ws/handoffs', token)
    const protocols = buildWebSocketProtocols(token)
    const ws = protocols ? new WebSocket(url, protocols) : new WebSocket(url)
    wsRef.current = ws
    setStatus('connecting')

    ws.onopen = () => {
      if (!mountedRef.current) return
      setStatus('connected')
      delayRef.current = BASE_DELAY_MS
      setReconnectCount((c) => c + 1)
    }

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return
      let msg
      try { msg = JSON.parse(evt.data) } catch { return }

      if (msg?.type === 'heartbeat') return

      if (msg?.type === 'handoff_update' && msg?.handoff_id) {
        const state = msg.state
        setLastMessageAt(Date.now())

        setHandoffs((prev) => {
          const id = msg.handoff_id
          if (state === 'confirmed' || state === 'rejected' || state === 'expired') {
            if (id in prev) {
              const next = { ...prev }
              delete next[id]
              return next
            }
            return prev
          }
          const updated = { ...prev, [id]: { ...(prev[id] ?? {}), ...msg } }
          const keys = Object.keys(updated)
          if (keys.length > MAX_HANDOFFS) {
            const toRemove = keys.slice(0, keys.length - MAX_HANDOFFS)
            toRemove.forEach((k) => delete updated[k])
          }
          return updated
        })
      }
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setStatus('error')
    }

    ws.onclose = event => {
      if (!mountedRef.current) return
      if (event.code === 1008) {
        setStatus('auth_error')
        return
      }
      setStatus('disconnected')
      const delay = delayRef.current
      delayRef.current = Math.min(delay * BACKOFF_FACTOR, MAX_DELAY_MS)
      retryRef.current = setTimeout(connect, delay)
    }
  }, [authRequired, token])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return {
    handoffs,
    handoffList: Object.values(handoffs),
    status,
    lastMessageAt,
    reconnectCount,
  }
}
