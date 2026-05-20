import { useCallback, useEffect, useState } from 'react'
import {
  cancelUploadedVideoProcessing,
  createCaseFromUploadedVideo,
  getUploadedVideoCommandCenterLinks,
  getUploadedVideoEvents,
  getUploadedVideoReport,
  getUploadedVideoSession,
  getUploadedVideoStatus,
  getUploadedVideoTimeline,
  listUploadedVideoSessions,
  startUploadedVideoProcessing,
  uploadUploadedVideo,
} from '../api/uploadedVideoApi'
import { useAuthGate } from './useAuthenticatedQuery'

function scopedUploadedVideoError(prefix, err) {
  const status = err?.status
  const message = err?.message || 'request failed'
  if (status === 401) return `${prefix}: session expired`
  if (status === 403) return `${prefix}: 403 permission denied`
  if (status === 404) return `${prefix}: endpoint not found`
  if (status) return `${prefix}: ${status} ${message}`
  return `${prefix}: ${message}`
}

const TERMINAL_STATES = new Set(['completed', 'failed', 'cancelled'])
const RUNNING_STATES = new Set(['queued', 'processing', 'frame_extraction', 'inference', 'event_generation', 'report_generation'])

function normalizeStatus(value) {
  return String(value || '').toLowerCase()
}

export function useUploadedVideo({ enabled = true, pollMs = 15000 } = {}) {
  const gate = useAuthGate('uploaded_video:read', { enabled })
  const [sessions, setSessions] = useState([])
  const [currentSession, setCurrentSession] = useState(null)
  const [currentStatus, setCurrentStatus] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [events, setEvents] = useState([])
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(Boolean(enabled))
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState(null)

  const refreshSessions = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setSessions([])
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
  }, [gate.enabled, gate.message, gate.reason])

  const refreshSessionDetail = useCallback(async (sessionId) => {
    if (!sessionId) {
      setCurrentSession(null)
      setCurrentStatus(null)
      setTimeline([])
      setEvents([])
      setReport(null)
      return null
    }
    setDetailLoading(true)
    try {
      const [session, nextStatus, nextTimeline, nextEvents] = await Promise.all([
        getUploadedVideoSession(sessionId),
        getUploadedVideoStatus(sessionId),
        getUploadedVideoTimeline(sessionId),
        getUploadedVideoEvents(sessionId),
      ])
      setCurrentSession(session)
      setCurrentStatus(nextStatus)
      setTimeline(nextTimeline)
      setEvents(nextEvents)
      const statusValue = normalizeStatus(nextStatus?.status || session?.status)
      let reportLoaded = false
      try {
        const nextReport = await getUploadedVideoReport(sessionId)
        let enrichedReport = nextReport
        try {
          const commandCenterLinks = await getUploadedVideoCommandCenterLinks(sessionId)
          if (commandCenterLinks && !enrichedReport?.metadata?.command_center) {
            enrichedReport = {
              ...enrichedReport,
              metadata: { ...(enrichedReport?.metadata || {}), command_center: commandCenterLinks },
            }
          }
        } catch {
          // Command-center links are also embedded in completed reports; this fallback is best effort.
        }
        setReport(enrichedReport)
        reportLoaded = Boolean(nextReport)
      } catch (err) {
        if (err?.status === 404) {
          setReport(null)
        } else {
          setError(scopedUploadedVideoError('Report load failed', err))
        }
      }
      if (statusValue === 'failed') {
        const failureReason = nextStatus?.last_error || session?.metadata?.last_error || 'Processing failed. Review backend logs for details.'
        setError(`Processing failed: ${failureReason}`)
      } else if (statusValue === 'completed' && !reportLoaded) {
        setError('Processing completed but the report artifact is not available yet.')
      } else if (!session?.status || statusValue === 'uploaded' || RUNNING_STATES.has(statusValue) || TERMINAL_STATES.has(statusValue)) {
        setError(null)
      } else {
        setError(`Unknown uploaded-video status: ${statusValue}`)
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
    if (gate.reason === 'disabled') return undefined
    const initialTimer = window.setTimeout(refreshSessions, 0)
    if (!gate.enabled) {
      return () => window.clearTimeout(initialTimer)
    }
    const timer = pollMs > 0 ? window.setInterval(refreshSessions, pollMs) : null
    return () => {
      window.clearTimeout(initialTimer)
      if (timer) window.clearInterval(timer)
    }
  }, [gate.enabled, gate.reason, pollMs, refreshSessions])

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
      setCurrentStatus(nextStatus)
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
      setCurrentStatus(nextStatus)
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
    currentStatus,
    timeline,
    events,
    report,
    loading,
    detailLoading,
    actionLoading,
    error,
    authGate: gate,
    refreshSessions,
    refreshSessionDetail,
    selectSession: refreshSessionDetail,
    upload,
    startProcessing,
    cancelProcessing,
    createCase,
  }
}
