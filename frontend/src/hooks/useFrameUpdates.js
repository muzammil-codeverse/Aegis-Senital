import { useCallback, useEffect, useRef, useState } from 'react'
import { WS_BASE_URL } from '../config'

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const RECONNECT_FACTOR = 2

export function useFrameUpdates() {
  const [framesByCameraId, setFramesByCameraId] = useState({})
  const [status, setStatus] = useState('disconnected')
  const wsRef = useRef(null)
  const reconnectDelayRef = useRef(RECONNECT_BASE_MS)
  const reconnectTimerRef = useRef(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return

    const url = `${WS_BASE_URL}/ws/frames`
    let ws
    try {
      ws = new WebSocket(url)
    } catch {
      scheduleReconnect()
      return
    }
    wsRef.current = ws
    setStatus('connecting')

    ws.onopen = () => {
      if (!mountedRef.current) return
      reconnectDelayRef.current = RECONNECT_BASE_MS
      setStatus('connected')
    }

    ws.onmessage = evt => {
      if (!mountedRef.current) return
      let msg
      try { msg = JSON.parse(evt.data) } catch { return }
      if (msg.type !== 'frame_update') return
      const { camera_id, frame_id } = msg
      if (!camera_id) return
      setFramesByCameraId(prev => {
        const existing = prev[camera_id]
        // Deduplicate by camera_id + frame_id
        if (existing && existing.frame_id === frame_id && frame_id != null) return prev
        return { ...prev, [camera_id]: msg }
      })
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setStatus('error')
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setStatus('disconnected')
      scheduleReconnect()
    }
  }, [])

  function scheduleReconnect() {
    if (!mountedRef.current) return
    const delay = reconnectDelayRef.current
    reconnectDelayRef.current = Math.min(delay * RECONNECT_FACTOR, RECONNECT_MAX_MS)
    reconnectTimerRef.current = setTimeout(connect, delay)
  }

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  return { framesByCameraId, status }
}
