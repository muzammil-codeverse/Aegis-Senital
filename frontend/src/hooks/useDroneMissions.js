/**
 * React hook for the Drone Patrol Mission Planner (Phase 45).
 * Handles mission list, session state, and live telemetry polling.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cancelSession,
  createMission,
  deleteMission,
  getSessionEvents,
  getSessionReport,
  getSessionStatus,
  getSessionTelemetry,
  listMissions,
  pauseSession,
  resumeSession,
  startMission,
} from '../api/droneMissionApi'

const POLL_INTERVAL_MS = 3000

export function useDroneMissions() {
  const [missions, setMissions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeSession, setActiveSession] = useState(null)
  const [telemetry, setTelemetry] = useState([])
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const pollRef = useRef(null)

  const fetchMissions = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listMissions()
      setMissions(data.items || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMissions()
  }, [fetchMissions])

  const handleCreate = useCallback(async (payload) => {
    const data = await createMission(payload)
    await fetchMissions()
    return data.item
  }, [fetchMissions])

  const handleDelete = useCallback(async (missionId) => {
    await deleteMission(missionId)
    await fetchMissions()
  }, [fetchMissions])

  const handleStart = useCallback(async (missionId) => {
    const data = await startMission(missionId)
    setActiveSession(data.item)
    setTelemetry([])
    setEvents([])
    setReport(null)
    startPolling(data.item.session_id)
    await fetchMissions()
    return data.item
  }, [fetchMissions])

  const handlePause = useCallback(async () => {
    if (!activeSession) return
    const data = await pauseSession(activeSession.session_id)
    setActiveSession(data.item)
  }, [activeSession])

  const handleResume = useCallback(async () => {
    if (!activeSession) return
    const data = await resumeSession(activeSession.session_id)
    setActiveSession(data.item)
  }, [activeSession])

  const handleCancel = useCallback(async () => {
    if (!activeSession) return
    const data = await cancelSession(activeSession.session_id)
    setActiveSession(data.item)
    stopPolling()
    await fetchMissions()
  }, [activeSession, fetchMissions])

  const startPolling = useCallback((sessionId) => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const statusData = await getSessionStatus(sessionId)
        setActiveSession(prev => prev ? { ...prev, ...statusData.item } : statusData.item)

        const telData = await getSessionTelemetry(sessionId)
        setTelemetry(telData.items || [])

        const evtData = await getSessionEvents(sessionId)
        setEvents(evtData.items || [])

        const s = statusData.item?.status
        if (s === 'completed' || s === 'cancelled' || s === 'failed') {
          stopPolling()
          try {
            const rptData = await getSessionReport(sessionId)
            setReport(rptData.item)
          } catch (_) {}
          await fetchMissions()
        }
      } catch (_) {}
    }, POLL_INTERVAL_MS)
  }, [fetchMissions])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  return {
    missions,
    loading,
    error,
    activeSession,
    telemetry,
    events,
    report,
    fetchMissions,
    handleCreate,
    handleDelete,
    handleStart,
    handlePause,
    handleResume,
    handleCancel,
  }
}
