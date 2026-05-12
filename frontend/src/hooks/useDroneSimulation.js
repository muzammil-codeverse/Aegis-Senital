import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { droneSimulationApi } from '../api/droneSimulationApi'
import { normalizeError } from '../api/client'
import { authUsesCookieMode, buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { useAuth } from './useAuth'

const DEFAULT_POLL_MS = 4000
const MAX_BACKOFF_MS = 30000

function mergeStatusPayload(item, setState) {
  setState(previous => ({
    session: item?.session ?? previous.session,
    connection: item?.connection ?? previous.connection,
    health: item?.health ?? previous.health,
    telemetry: item?.telemetry ?? previous.telemetry,
    latestFrameAvailable: Boolean(item?.latest_frame_available ?? previous.latestFrameAvailable),
  }))
}

export function useDroneSimulation({ enabled = true, pollMs = DEFAULT_POLL_MS } = {}) {
  const auth = useAuth()
  const canRead = enabled && auth.hasPermission('drone:read')
  const canControl = auth.hasPermission('drone:control')
  const [status, setStatus] = useState({
    session: null,
    connection: null,
    health: null,
    telemetry: null,
    latestFrameAvailable: false,
  })
  const [flightPath, setFlightPath] = useState([])
  const [latestFrame, setLatestFrame] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [wsStatus, setWsStatus] = useState(canRead ? 'connecting' : 'disabled')
  const [lastTelemetryAt, setLastTelemetryAt] = useState(null)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const closeRequestedRef = useRef(false)
  const socketRef = useRef(null)

  const refreshAll = useCallback(async () => {
    if (!canRead) return
    setLoading(true)
    try {
      const [statusResponse, pathResponse, frameResponse] = await Promise.all([
        droneSimulationApi.getStatus(),
        droneSimulationApi.getFlightPath(),
        droneSimulationApi.getLatestFrame(),
      ])
      mergeStatusPayload(statusResponse.item, setStatus)
      setFlightPath(pathResponse.items || [])
      setLatestFrame(frameResponse.item || null)
      setLastTelemetryAt(statusResponse.item?.telemetry?.timestamp || Date.now())
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [canRead])

  const refreshFrame = useCallback(async () => {
    if (!canRead) return
    try {
      const response = await droneSimulationApi.getLatestFrame()
      setLatestFrame(response.item || null)
    } catch (err) {
      setError(normalizeError(err))
    }
  }, [canRead])

  useEffect(() => {
    if (!canRead) {
      setWsStatus('disabled')
      return undefined
    }
    refreshAll()
    if (!pollMs) return undefined
    const timer = window.setInterval(refreshAll, pollMs)
    return () => window.clearInterval(timer)
  }, [canRead, pollMs, refreshAll])

  useEffect(() => {
    if (!canRead) {
      setWsStatus('disabled')
      return undefined
    }
    if (auth.authRequired && !auth.token && !authUsesCookieMode()) {
      setWsStatus('auth_error')
      return undefined
    }
    closeRequestedRef.current = false

    function connect() {
      const url = buildWebSocketUrl('/ws/drone-simulation', auth.token)
      const protocols = buildWebSocketProtocols(auth.token)
      setWsStatus(reconnectRef.current > 0 ? 'reconnecting' : 'connecting')
      const socket = protocols ? new WebSocket(url, protocols) : new WebSocket(url)
      socketRef.current = socket

      socket.onopen = () => {
        reconnectRef.current = 0
        setWsStatus('open')
      }

      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data)
          if (message?.event_type !== 'drone_telemetry') return
          setStatus(previous => ({
            ...previous,
            telemetry: message.telemetry ?? previous.telemetry,
            session: message.session ?? previous.session,
          }))
          setLastTelemetryAt(message.timestamp || Date.now())
          setError(null)
        } catch (err) {
          console.warn('Unable to parse drone simulation websocket message', err)
        }
      }

      socket.onerror = () => {
        setWsStatus('error')
      }

      socket.onclose = event => {
        if (closeRequestedRef.current) {
          setWsStatus('closed')
          return
        }
        if (event.code === 1008) {
          setWsStatus('auth_error')
          return
        }
        reconnectRef.current += 1
        setWsStatus('reconnecting')
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.min(reconnectRef.current, 5))
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closeRequestedRef.current = true
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      socketRef.current?.close()
    }
  }, [auth.authRequired, auth.token, canRead])

  const runAction = useCallback(
    async action => {
      setActionError(null)
      try {
        const response = await action()
        await refreshAll()
        return response.item || null
      } catch (err) {
        setActionError(normalizeError(err))
        return null
      }
    },
    [refreshAll],
  )

  const startSession = useCallback(() => runAction(() => droneSimulationApi.startSession()), [runAction])
  const stopSession = useCallback(() => runAction(() => droneSimulationApi.stopSession()), [runAction])
  const takeoff = useCallback(() => runAction(() => droneSimulationApi.takeoff()), [runAction])
  const land = useCallback(() => runAction(() => droneSimulationApi.land()), [runAction])
  const hover = useCallback(() => runAction(() => droneSimulationApi.hover()), [runAction])
  const move = useCallback(payload => runAction(() => droneSimulationApi.move(payload)), [runAction])

  const stats = useMemo(() => {
    const processing = latestFrame?.metadata?.processing_result || {}
    return {
      events: Number(processing.events || 0),
      anomalies: Number(processing.anomalies || 0),
      incidents: Number(processing.incidents || 0),
      framesProcessed: Number(status.session?.frames_processed_total || 0),
      telemetryUpdates: Number(status.session?.telemetry_updates_total || 0),
    }
  }, [latestFrame, status.session])

  return {
    canRead,
    canControl,
    status,
    telemetry: status.telemetry,
    flightPath,
    latestFrame,
    stats,
    wsStatus,
    loading,
    error,
    actionError,
    lastTelemetryAt,
    refreshAll,
    refreshFrame,
    startSession,
    stopSession,
    takeoff,
    land,
    hover,
    move,
  }
}
