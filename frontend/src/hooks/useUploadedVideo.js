import { useCallback, useEffect, useState } from 'react'
import {
  cancelUploadedVideoProcessing,
  createCaseFromUploadedVideo,
  getUploadedVideoEvents,
  getUploadedVideoReport,
  getUploadedVideoSession,
  getUploadedVideoTimeline,
  listUploadedVideoSessions,
  startUploadedVideoProcessing,
  uploadUploadedVideo,
} from '../api/uploadedVideoApi'

function scopedUploadedVideoError(prefix, err) {
  const status = err?.status
  const message = err?.message || 'request failed'
  if (status === 401) return `${prefix}: auth required`
  if (status === 403) return `${prefix}: 403 permission denied`
  if (status === 404) return `${prefix}: endpoint not found`
  if (status) return `${prefix}: ${status} ${message}`
  return `${prefix}: ${message}`
}

export function useUploadedVideo({ enabled = true, pollMs = 15000 } = {}) {
  const [sessions, setSessions] = useState([])
  const [currentSession, setCurrentSession] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(Boolean(enabled))
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState(null)

  const refreshSessions = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return []
    }
    try {
      const response = await listUploadedVideoSessions()
      setSessions(response.items)
      setError(null)
      return response.items
    } catch (err) {
      setError(scopedUploadedVideoError('Session list unavailable', err))
      return []
    } finally {
      setLoading(false)
    }
  }, [enabled])

  const refreshSessionDetail = useCallback(async (sessionId) => {
    if (!sessionId) {
      setCurrentSession(null)
      setTimeline([])
      setEvents([])
      setReport(null)
      return null
    }
    setDetailLoading(true)
    try {
      const [session, nextTimeline, nextEvents] = await Promise.all([
        getUploadedVideoSession(sessionId),
        getUploadedVideoTimeline(sessionId),
        getUploadedVideoEvents(sessionId),
      ])
      setCurrentSession(session)
      setTimeline(nextTimeline)
      setEvents(nextEvents)
      try {
        const nextReport = await getUploadedVideoReport(sessionId)
        setReport(nextReport)
      } catch (err) {
        if (err?.status === 404) {
          setReport(null)
        } else {
          setError(scopedUploadedVideoError('Report load failed', err))
        }
      }
      if (!session?.status || ['uploaded', 'queued'].includes(String(session.status).toLowerCase())) {
        setError('Upload accepted, waiting for processing.')
      } else {
        setReport(null)
      }
      return session
    } catch (err) {
      setError(scopedUploadedVideoError('Session detail unavailable', err))
      return null
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshSessions()
    if (!enabled) return undefined
    const timer = window.setInterval(refreshSessions, pollMs)
    return () => window.clearInterval(timer)
  }, [enabled, pollMs, refreshSessions])

  const upload = useCallback(async (file, options = {}) => {
    setActionLoading(true)
    try {
      const payload = await uploadUploadedVideo(file, options)
      const session = payload?.session || null
      await refreshSessions()
      if (session?.session_id) {
        await refreshSessionDetail(session.session_id)
      }
      setError(null)
      return session
    } catch (err) {
      setError(scopedUploadedVideoError('Upload request failed', err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [refreshSessionDetail, refreshSessions])

  const startProcessing = useCallback(async (sessionId) => {
    setActionLoading(true)
    try {
      const nextStatus = await startUploadedVideoProcessing(sessionId)
      await refreshSessionDetail(sessionId)
      await refreshSessions()
      setError(null)
      return nextStatus
    } catch (err) {
      setError(scopedUploadedVideoError('Processing start failed', err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [refreshSessionDetail, refreshSessions])

  const cancelProcessing = useCallback(async (sessionId) => {
    setActionLoading(true)
    try {
      const nextStatus = await cancelUploadedVideoProcessing(sessionId)
      await refreshSessionDetail(sessionId)
      await refreshSessions()
      setError(null)
      return nextStatus
    } catch (err) {
      setError(scopedUploadedVideoError('Processing cancel failed', err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [refreshSessionDetail, refreshSessions])

  const createCase = useCallback(async (sessionId, payload = {}) => {
    setActionLoading(true)
    try {
      const created = await createCaseFromUploadedVideo(sessionId, payload)
      await refreshSessionDetail(sessionId)
      await refreshSessions()
      setError(null)
      return created
    } catch (err) {
      setError(scopedUploadedVideoError('Case creation failed', err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [refreshSessionDetail, refreshSessions])

  return {
    sessions,
    currentSession,
    timeline,
    events,
    report,
    loading,
    detailLoading,
    actionLoading,
    error,
    refreshSessions,
    refreshSessionDetail,
    selectSession: refreshSessionDetail,
    upload,
    startProcessing,
    cancelProcessing,
    createCase,
  }
}
