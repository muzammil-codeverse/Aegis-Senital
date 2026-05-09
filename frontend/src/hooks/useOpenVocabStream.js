import { useState, useEffect, useRef, useCallback } from 'react'

const WS_RECONNECT_DELAY_MS = 3000
const WS_MAX_RECONNECT_ATTEMPTS = 10

/**
 * Phase 25 — useOpenVocabStream
 *
 * Connects to /ws/open-vocab and delivers live Open-Vocab scan results.
 * Falls back gracefully if the WebSocket is unavailable or disconnects.
 * Never surfaces raw frames or embeddings.
 */
export function useOpenVocabStream({ enabled = true, onScanResult } = {}) {
  const [connected, setConnected] = useState(false)
  const [transport, setTransport] = useState('disconnected') // 'websocket' | 'polling_fallback' | 'disconnected'
  const [lastResult, setLastResult] = useState(null)
  const [streamError, setStreamError] = useState(null)

  // Per-camera threat state: { [camera_id]: { result, badge, riskLevel, latestScanTime } }
  const [cameraState, setCameraState] = useState({})

  const wsRef = useRef(null)
  const reconnectCount = useRef(0)
  const reconnectTimer = useRef(null)
  const mountedRef = useRef(true)

  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'heartbeat') return
      if (msg.type !== 'open_vocab_scan_result') return

      const data = msg.data
      if (!data) return

      const cameraId = data.camera_id || 'unknown'
      const summary = data.summary || {}
      const detections = data.detections || []
      const highestRisk = summary.highest_risk_level || 'low'
      const detectionCount = summary.detection_count || 0

      const entry = {
        scanId: data.scan_id,
        cameraId,
        timestamp: data.timestamp,
        provider: data.provider,
        device: data.device,
        modelLoaded: data.model_loaded,
        prompts: data.prompts || [],
        detections,
        summary,
        riskLevel: highestRisk,
        hasThreat: detectionCount > 0,
        latestScanTime: data.timestamp,
      }

      setLastResult(entry)
      setCameraState(prev => ({ ...prev, [cameraId]: entry }))

      if (onScanResult) {
        onScanResult(entry)
      }
    } catch {
      // non-JSON or unexpected message — ignore
    }
  }, [onScanResult])

  const connect = useCallback(() => {
    if (!enabled || !mountedRef.current) return

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsHost = window.location.host
    const url = `${wsProtocol}://${wsHost}/ws/open-vocab`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      reconnectCount.current = 0
      setConnected(true)
      setTransport('websocket')
      setStreamError(null)
    }

    ws.onmessage = handleMessage

    ws.onerror = () => {
      if (!mountedRef.current) return
      setStreamError('WebSocket connection error')
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      setTransport('polling_fallback')

      if (reconnectCount.current < WS_MAX_RECONNECT_ATTEMPTS) {
        reconnectCount.current += 1
        reconnectTimer.current = setTimeout(connect, WS_RECONNECT_DELAY_MS)
      } else {
        setTransport('disconnected')
        setStreamError('WebSocket unavailable — using polling fallback')
      }
    }
  }, [enabled, handleMessage])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) {
      connect()
    }
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [enabled, connect])

  const getCameraEntry = useCallback((cameraId) => {
    return cameraState[cameraId] || null
  }, [cameraState])

  return {
    connected,
    transport,
    lastResult,
    streamError,
    cameraState,
    getCameraEntry,
  }
}
