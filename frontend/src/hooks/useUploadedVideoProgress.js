import { useCallback, useEffect, useRef, useState } from 'react'
import { buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { getStoredToken } from '../api/client'
import { getUploadedVideoStatus } from '../api/uploadedVideoApi'
import { normalizeError } from '../api/client'
import { useAuth } from './useAuth'

const POLL_MS = 2000
const MAX_BACKOFF_MS = 30000
const STALL_THRESHOLD_MS = 60_000
const RUNNING_STATES = new Set(['queued', 'processing', 'frame_extraction', 'inference', 'event_generation', 'report_generation'])

export function useUploadedVideoProgress(sessionId, { enabled = true } = {}) {
  const auth = useAuth()
  const authReady = Boolean(auth.ready ?? !auth.loading)
  const [status, setStatus] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [stalled, setStalled] = useState(false)

  // Track last time we saw progress change to detect stall
  const lastProgressRef = useRef({ percent: -1, at: Date.now() })
  const stallTimerRef = useRef(null)

  const updateStallTracker = useCallback((next) => {
    if (!next) return
    const pct = next?.progress?.percent ?? -1
    const statusVal = String(next?.status || '').toLowerCase()
    if (!RUNNING_STATES.has(statusVal)) {
      setStalled(false)
      if (stallTimerRef.current) {
        window.clearTimeout(stallTimerRef.current)
        stallTimerRef.current = null
      }
      return
    }
    if (pct !== lastProgressRef.current.percent) {
      lastProgressRef.current = { percent: pct, at: Date.now() }
      setStalled(false)
    }
    // Use backend heartbeat timestamp if available
    const backendTs = next?.last_progress_at ? new Date(next.last_progress_at).getTime() : null
    const referenceTs = backendTs && Number.isFinite(backendTs) ? backendTs : lastProgressRef.current.at
    if (Date.now() - referenceTs > STALL_THRESHOLD_MS) {
      setStalled(true)
    }
  }, [])

  useEffect(() => {
    if (!authReady || !auth.authenticated || !enabled || !sessionId) {
      const resetTimer = window.setTimeout(() => {
        setStatus(null)
        setConnectionStatus('idle')
        setStalled(false)
      }, 0)
      return () => window.clearTimeout(resetTimer)
    }

    let closed = false
    let socket = null
    let pollTimer = null
    let reconnectTimer = null
    let reconnectAttempts = 0
    let terminal = false
    lastProgressRef.current = { percent: -1, at: Date.now() }

    async function poll() {
      try {
        const next = await getUploadedVideoStatus(sessionId)
        if (!closed) {
          setStatus(next)
          updateStallTracker(next)
          setConnectionStatus(current => (current === 'auth_error' ? current : 'polling'))
          setError(null)
          terminal = Boolean(next?.status && ['completed', 'failed', 'cancelled'].includes(next.status))
        }
      } catch (err) {
        if (!closed) setError(normalizeError(err))
      }
      if (!closed && !terminal) {
        pollTimer = window.setTimeout(poll, POLL_MS)
      }
    }

    function connect() {
      const token = getStoredToken() || auth.token
      const url = buildWebSocketUrl(`/ws/uploaded-video/${encodeURIComponent(sessionId)}`, token)
      const protocols = buildWebSocketProtocols(token)
      setConnectionStatus(reconnectAttempts > 0 ? 'reconnecting' : 'connecting')
      socket = protocols ? new WebSocket(url, protocols) : new WebSocket(url)

      socket.onopen = () => {
        reconnectAttempts = 0
        setConnectionStatus('open')
      }

      socket.onmessage = event => {
        try {
          const payload = JSON.parse(event.data)
          setStatus(payload)
          updateStallTracker(payload)
          setConnectionStatus('open')
          setError(null)
          if (payload?.status && ['completed', 'failed', 'cancelled'].includes(payload.status)) {
            terminal = true
            socket?.close()
          }
        } catch (err) {
          setError(normalizeError(err))
        }
      }

      socket.onerror = () => {
        setConnectionStatus('error')
      }

      socket.onclose = event => {
        if (closed) return
        if (terminal) {
          setConnectionStatus('closed')
          return
        }
        if (event.code === 1008) {
          setConnectionStatus('auth_error')
          poll()
          return
        }
        reconnectAttempts += 1
        setConnectionStatus('reconnecting')
        reconnectTimer = window.setTimeout(connect, Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.min(reconnectAttempts, 5)))
      }
    }

    connect()
    poll()

    return () => {
      closed = true
      if (pollTimer) window.clearTimeout(pollTimer)
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      if (stallTimerRef.current) window.clearTimeout(stallTimerRef.current)
      socket?.close()
    }
  }, [auth.authenticated, auth.token, authReady, enabled, sessionId, updateStallTracker])

  return { status, connectionStatus, error, stalled }
}
