import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { droneSimulationApi } from '../api/droneSimulationApi'
import { authUsesCookieMode, buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { useAuth } from './useAuth'

const DEFAULT_POLL_MS = 4000
const MAX_BACKOFF_MS = 30000
const MAX_RECONNECT_ATTEMPTS = 8

function formatScopedError(prefix, err) {
  if (!err) return `${prefix}: unknown error`
  const status = err?.status ? `${err.status}` : null
  const kind = err?.kind || err?.details?.kind || null
  const detail = err?.message || 'request failed'
  if (status === '403') return `${prefix}: 403 permission denied`
  if (status === '404') return `${prefix}: endpoint not found`
  if (status) return `${prefix}: ${status} ${detail}`
  if (kind === 'network') return `${prefix}: backend unreachable`
  return `${prefix}: ${detail}`
}

function mergeStatusPayload(item, setState) {
  setState(previous => ({
    session: item?.session ?? previous.session,
    connection: item?.connection ?? previous.connection,
    health: item?.health ?? previous.health,
    runtimeStatus: item?.runtime_status ?? previous.runtimeStatus,
    cameraSources: item?.camera_sources ?? previous.cameraSources,
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
    runtimeStatus: null,
    cameraSources: [],
    telemetry: null,
    latestFrameAvailable: false,
  })
  const [flightPath, setFlightPath] = useState([])
  const [latestFrame, setLatestFrame] = useState(null)
  const [cameraFrames, setCameraFrames] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [wsStatus, setWsStatus] = useState(canRead ? 'connecting' : 'disabled')
  const [uiState, setUiState] = useState('not_started')
  const [statusDetail, setStatusDetail] = useState('Signed in, waiting for runtime status.')
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
      const [runtimeResponse, camerasResponse] = await Promise.all([
        droneSimulationApi.getRuntimeStatus().catch(() => ({ item: null })),
        droneSimulationApi.listCameras().catch(() => ({ items: [] })),
      ])
      mergeStatusPayload(statusResponse.item, setStatus)
      if (runtimeResponse?.item) {
        setStatus(previous => ({ ...previous, runtimeStatus: runtimeResponse.item }))
      }
      if (Array.isArray(camerasResponse?.items)) {
        setStatus(previous => ({ ...previous, cameraSources: camerasResponse.items }))
      }
      setFlightPath(pathResponse.items || [])
      setLatestFrame(frameResponse.item || null)
      if (frameResponse.item?.camera_name) {
        setCameraFrames(previous => ({ ...previous, [frameResponse.item.camera_name]: frameResponse.item }))
      }
      setLastTelemetryAt(statusResponse.item?.telemetry?.timestamp || Date.now())
      const nextSession = statusResponse?.item?.session || {}
      const nextHealth = statusResponse?.item?.health || {}
      const nextRuntime = statusResponse?.item?.runtime_status || runtimeResponse?.item || {}
      if (nextSession?.active) {
        setUiState('running')
        setStatusDetail('Simulated drone session is running.')
      } else if (nextRuntime?.connected) {
        setUiState(nextHealth?.status === 'degraded' ? 'degraded' : 'not_started')
        setStatusDetail(nextHealth?.status === 'degraded'
          ? (nextHealth?.detail || 'AirSimNH connected with degraded runtime checks.')
          : 'Ready to start simulated drone session.')
      } else {
        setUiState('disconnected')
        setStatusDetail('Drone runtime disconnected.')
      }
      setError(null)
    } catch (err) {
      setUiState('error')
      setStatusDetail(formatScopedError('Drone status load failed', err))
      setError(formatScopedError('Drone status load failed', err))
    } finally {
      setLoading(false)
    }
  }, [canRead])

  const refreshFrame = useCallback(async () => {
    if (!canRead) return
    try {
      const response = await droneSimulationApi.getLatestFrame()
      setLatestFrame(response.item || null)
      if (response.item?.camera_name) {
        setCameraFrames(previous => ({ ...previous, [response.item.camera_name]: response.item }))
      }
    } catch (err) {
      setError(formatScopedError('Latest frame fetch failed', err))
    }
  }, [canRead])

  const refreshCameraFrame = useCallback(async cameraName => {
    if (!canRead || !cameraName) return null
    try {
      const response = await droneSimulationApi.getCameraLatestFrame(cameraName)
      if (response.item) {
        setCameraFrames(previous => ({ ...previous, [cameraName]: response.item }))
      }
      return response.item || null
    } catch (err) {
      setError(formatScopedError(`Camera ${cameraName} frame fetch failed`, err))
      return null
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
        setUiState(previous => (previous === 'disconnected' ? 'degraded' : previous))
        setStatusDetail(previous => (
          previous?.includes('Ready to start')
            ? previous
            : 'Live websocket connected.'
        ))
      }

      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data)
          const messageType = String(message?.type || '').toLowerCase()
          const eventType = String(message?.event_type || '').toLowerCase()
          if (messageType === 'telemetry' || eventType === 'drone_telemetry') {
            const data = message?.data || {}
            setStatus(previous => ({
              ...previous,
              telemetry: data.telemetry ?? message.telemetry ?? previous.telemetry,
              session: data.session ?? message.session ?? previous.session,
            }))
            setLastTelemetryAt(message.timestamp || Date.now())
          }
          if (messageType === 'runtime_status') {
            const data = message?.data || {}
            setStatus(previous => ({
              ...previous,
              runtimeStatus: {
                ...previous.runtimeStatus,
                ...data,
              },
            }))
          }
          if (messageType === 'frame_status') {
            const data = message?.data || {}
            if (data?.camera_name) {
              setCameraFrames(previous => ({
                ...previous,
                [data.camera_name]: {
                  ...previous[data.camera_name],
                  camera_name: data.camera_name,
                  frame_available: Boolean(data.frame_available),
                  frame_index: data.frame_index,
                  status: data.status,
                  last_error: data.last_error || null,
                },
              }))
            }
          }
          setError(null)
          if (messageType === 'telemetry' && !status?.session?.active) {
            setUiState('running')
          }
        } catch (err) {
          console.warn('Unable to parse drone simulation websocket message', err)
        }
      }

      socket.onerror = () => {
        setWsStatus('error')
        setStatusDetail('WebSocket error. Live polling active.')
      }

      socket.onclose = event => {
        if (closeRequestedRef.current) {
          setWsStatus('closed')
          return
        }
        if (event.code === 1008 || event.code === 4401 || event.code === 4403) {
          setWsStatus('auth_error')
          setStatusDetail('Drone websocket authentication required. Live polling active.')
          return
        }
        if (reconnectRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setWsStatus('degraded')
          setStatusDetail('WebSocket unavailable. Live polling active.')
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
        setUiState('starting')
        const response = await action()
        await refreshAll()
        setUiState('running')
        return response.item || null
      } catch (err) {
        setUiState('error')
        setActionError(formatScopedError('Session action failed', err))
        return null
      }
    },
    [refreshAll],
  )

  const startSession = useCallback(() => runAction(() => droneSimulationApi.startSession()), [runAction])
  const stopSession = useCallback(() => runAction(() => droneSimulationApi.stopSession()), [runAction])
  const launchRuntime = useCallback(prefer => runAction(() => droneSimulationApi.launchRuntime(prefer || 'AirSimNH')), [runAction])
  const runMissionDemo = useCallback(mission => runAction(() => droneSimulationApi.runMissionDemo(mission || 'fixed_camera_handoff_demo')), [runAction])
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
    runtimeStatus: status.runtimeStatus,
    cameraSources: status.cameraSources || [],
    flightPath,
    latestFrame,
    cameraFrames,
    stats,
    wsStatus,
    uiState,
    statusDetail,
    loading,
    error,
    actionError,
    lastTelemetryAt,
    refreshAll,
    refreshFrame,
    refreshCameraFrame,
    startSession,
    stopSession,
    launchRuntime,
    runMissionDemo,
    takeoff,
    land,
    hover,
    move,
  }
}
