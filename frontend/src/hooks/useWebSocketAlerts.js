import { useEffect, useMemo, useRef, useState } from 'react'
import { authUsesCookieMode, buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { useAuth } from './useAuth'

const MAX_BUFFER = 200
const SLOW_AFTER_MS = 90_000
const MAX_BACKOFF_MS = 30_000

export function useWebSocketAlerts() {
  const { token, authRequired } = useAuth()
  const [alertsById, setAlertsById] = useState({})
  const [status, setStatus] = useState('connecting')
  const [lastMessageAt, setLastMessageAt] = useState(null)
  const [reconnectCount, setReconnectCount] = useState(0)
  const reconnectRef = useRef(0)
  const socketRef = useRef(null)
  const closeRequestedRef = useRef(false)
  const reconnectTimerRef = useRef(null)

  useEffect(() => {
    if (authRequired && !token && !authUsesCookieMode()) {
      setStatus('auth_error')
      return undefined
    }
    closeRequestedRef.current = false

    function connect() {
      const url = buildWebSocketUrl('/ws/alerts', token)
      const protocols = buildWebSocketProtocols(token)
      setStatus(reconnectRef.current > 0 ? 'reconnecting' : 'connecting')
      const socket = protocols ? new WebSocket(url, protocols) : new WebSocket(url)
      socketRef.current = socket

      socket.onopen = () => {
        setStatus('open')
        reconnectRef.current = 0
      }

      socket.onmessage = event => {
        setLastMessageAt(Date.now())
        setStatus('open')
        let message
        try {
          message = JSON.parse(event.data)
        } catch (err) {
          console.warn('Unable to parse alert websocket message', err)
          return
        }
        if (message?.type === 'heartbeat') {
          return
        }
        const alert = normalizeAlertMessage(message)
        if (!alert?.alert_id) {
          return
        }
        setAlertsById(previous => {
          const next = { ...previous, [alert.alert_id]: { ...previous[alert.alert_id], ...alert } }
          const ordered = Object.values(next)
            .sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))
            .slice(0, MAX_BUFFER)
          return ordered.reduce((acc, item) => ({ ...acc, [item.alert_id]: item }), {})
        })
      }

      socket.onerror = () => {
        setStatus('error')
      }

      socket.onclose = event => {
        if (closeRequestedRef.current) {
          setStatus('closed')
          return
        }
        if (event.code === 1008) {
          setStatus('auth_error')
          return
        }
        reconnectRef.current += 1
        setReconnectCount(count => count + 1)
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.min(reconnectRef.current, 5))
        setStatus('reconnecting')
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closeRequestedRef.current = true
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      socketRef.current?.close()
    }
  }, [authRequired, token])

  useEffect(() => {
    const slowTimer = window.setInterval(() => {
      if (lastMessageAt && Date.now() - lastMessageAt > SLOW_AFTER_MS && socketRef.current?.readyState === WebSocket.OPEN) {
        setStatus('slow')
      }
    }, 5000)
    return () => window.clearInterval(slowTimer)
  }, [lastMessageAt])

  const alerts = useMemo(() => (
    Object.values(alertsById).sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))
  ), [alertsById])

  return { alerts, status, lastMessageAt, reconnectCount }
}

function normalizeAlertMessage(message) {
  const payload = message?.payload || message?.alert || message
  if (payload?.alert_id) return payload
  if (payload?.payload?.alert_id) return payload.payload
  return null
}
