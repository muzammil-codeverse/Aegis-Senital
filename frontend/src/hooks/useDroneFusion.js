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

export function useDroneFusion({ caseId, eventId } = {}) {
  const [observations, setObservations] = useState([])
  const [correlations, setCorrelations] = useState([])
  const [handoffs, setHandoffs] = useState([])
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  const fetchAll = useCallback(async () => {
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
  }, [caseId, eventId])

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

  const suggestHandoffs = useCallback(async (eventId_) => {
    try {
      const result = await suggestHandoffsForEvent({ event_id: eventId_ || eventId, radius_meters: 200 })
      await fetchAll()
      return result
    } catch (err) {
      setError(err?.message || 'Handoff suggestion failed')
    }
  }, [eventId, fetchAll])

  // WebSocket for live fusion events
  const connectWs = useCallback(() => {
    if (wsRef.current) return
    try {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/ws/drone-fusion`)
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data)
          if (data.event_type === 'fusion_correlation_created' || data.event_type?.startsWith('fusion_')) {
            fetchAll()
          }
        } catch {}
      }
      ws.onclose = () => { wsRef.current = null }
      wsRef.current = ws
    } catch {}
  }, [fetchAll])

  useEffect(() => {
    connectWs()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connectWs])

  return {
    observations,
    correlations,
    handoffs,
    timeline,
    loading,
    error,
    fetchAll,
    correlate,
    reviewCorrelation,
    suggestHandoffs,
  }
}
