import { useEffect, useState } from 'react'
import { buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { getStoredToken } from '../api/client'
import { getUploadedVideoStatus } from '../api/uploadedVideoApi'
import { normalizeError } from '../api/client'
import { useAuth } from './useAuth'

const POLL_MS = 2000
const MAX_BACKOFF_MS = 30000

export function useUploadedVideoProgress(sessionId, { enabled = true } = {}) {
  const auth = useAuth()
  const [status, setStatus] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('idle')
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!enabled || !sessionId) {
      setStatus(null)
      setConnectionStatus('idle')
      return undefined
    }

    let closed = false
    let socket = null
    let pollTimer = null
    let reconnectTimer = null
    let reconnectAttempts = 0
    let terminal = false

    async function poll() {
      try {
        const next = await getUploadedVideoStatus(sessionId)
        if (!closed) {
          setStatus(next)
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
      socket?.close()
    }
  }, [auth.token, enabled, sessionId])

  return { status, connectionStatus, error }
}
