import { useCallback, useEffect, useRef, useState } from 'react'
import {
  acceptCorrelation,
  getFusionTimeline,
  listCorrelations,
  listFusionObservations,
  listHandoffs,
  markCorrelationInconclusive,
  rejectCorrelation,
  runCorrelation,
  suggestHandoffsForEvent,
} from '../api/droneFusionApi'
import { authUsesCookieMode, buildWebSocketProtocols, buildWebSocketUrl } from '../config'
import { useAuth } from './useAuth'

const MAX_BACKOFF_MS = 30000
const MAX_RECONNECT_ATTEMPTS = 8

export function useDroneFusion({ caseId, eventId } = {}) {
  const auth = useAuth()
  const canRead = auth.hasPermission('drone_fusion:read')
  const [observations, setObservations] = useState([])
  const [correlations, setCorrelations] = useState([])
  const [handoffs, setHandoffs] = useState([])
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [wsStatus, setWsStatus] = useState(canRead ? 'connecting' : 'disabled')
  const [reconnectCount, setReconnectCount] = useState(0)
  const wsRef = useRef(null)
  const reconnectRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const closeRequestedRef = useRef(false)

  const fetchAll = useCallback(async () => {
    if (!canRead) return
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (caseId) params.case_id = caseId
      if (eventId) params.event_id = eventId
      const [obsResult, corrResult, handoffResult, tlResult] = await Promise.all([
        listFusionObservations(params),
        listCorrelations(params),
        listHandoffs(params),
        getFusionTimeline(params).catch(() => null),
      ])
      setObservations(obsResult?.items || obsResult?.observations || [])
      setCorrelations(corrResult?.items || corrResult?.correlations || [])
      setHandoffs(handoffResult?.items || handoffResult?.handoffs || [])
      setTimeline(tlResult)
    } catch (err) {
      setError(err?.message || 'Failed to load fusion data')
    } finally {
      setLoading(false)
    }
  }, [canRead, caseId, eventId])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const correlate = useCallback(async (opts = {}) => {
    setLoading(true)
    try {
      const result = await runCorrelation({ case_id: caseId, event_id: eventId, ...opts })
      await fetchAll()
      return result
    } catch (err) {
      setError(err?.message || 'Correlation failed')
      return null
    } finally {
      setLoading(false)
    }
  }, [caseId, eventId, fetchAll])

  const reviewCorrelation = useCallback(async (correlationId, action, notes) => {
    try {
      if (action === 'accept') await acceptCorrelation(correlationId, notes)
      else if (action === 'reject') await rejectCorrelation(correlationId, notes)
      else await markCorrelationInconclusive(correlationId, notes)
      await fetchAll()
    } catch (err) {
      setError(err?.message || 'Review action failed')
    }
  }, [fetchAll])

  const suggestHandoffs = useCallback(async eventId_ => {
    try {
      const result = await suggestHandoffsForEvent({ event_id: eventId_ || eventId, radius_meters: 200 })
      await fetchAll()
      return result
    } catch (err) {
      setError(err?.message || 'Handoff suggestion failed')
      return null
    }
  }, [eventId, fetchAll])

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
      const url = buildWebSocketUrl('/ws/drone-fusion', auth.token)
      const protocols = buildWebSocketProtocols(auth.token)
      setWsStatus(reconnectRef.current > 0 ? 'reconnecting' : 'connecting')
      const ws = protocols ? new WebSocket(url, protocols) : new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectRef.current = 0
        setWsStatus('open')
      }

      ws.onmessage = evt => {
        try {
          const data = JSON.parse(evt.data)
          if (
            data?.event_type === 'fusion_correlation_created'
            || data?.event_type === 'fusion_correlation_accepted'
            || data?.event_type === 'fusion_correlation_rejected'
            || data?.event_type === 'fusion_handoff_suggested'
          ) {
            fetchAll()
          }
        } catch {}
      }

      ws.onerror = () => {
        setWsStatus('error')
      }

      ws.onclose = event => {
        wsRef.current = null
        if (closeRequestedRef.current) {
          setWsStatus('closed')
          return
        }
        if (event.code === 1008 || event.code === 4401 || event.code === 4403) {
          setWsStatus('auth_error')
          return
        }
        if (reconnectRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setWsStatus('degraded')
          return
        }
        reconnectRef.current += 1
        setReconnectCount(count => count + 1)
        setWsStatus('reconnecting')
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.min(reconnectRef.current, 5))
        reconnectTimerRef.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closeRequestedRef.current = true
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [auth.authRequired, auth.token, canRead, fetchAll])

  return {
    observations,
    correlations,
    handoffs,
    timeline,
    loading,
    error,
    wsStatus,
    reconnectCount,
    fetchAll,
    correlate,
    reviewCorrelation,
    suggestHandoffs,
  }
}
