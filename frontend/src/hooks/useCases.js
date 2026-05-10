import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  addEvidence,
  addNote,
  archiveCase,
  assignCase,
  closeCase,
  createCase,
  createCaseFromEvent,
  dismissCase,
  exportCase,
  getCase,
  getTimeline,
  listCases,
  listEvidence,
  listNotes,
  reopenCase,
  updateCase,
} from '../api/caseApi'
import {
  askCaseQuestion,
  draftCaseReport,
  getLlmStatus,
  summarizeCase,
  summarizeEvidence,
  summarizeTimeline,
  verifyLlmProvider,
} from '../api/llmApi'
import { normalizeError } from '../api/client'

const DEFAULT_FILTERS = {
  status: '',
  priority: '',
  camera: '',
  tag: '',
  q: '',
}

export function useCases({ enabled = true, pollMs = 15000, initialFilters = {} } = {}) {
  const [cases, setCases] = useState([])
  const [selectedCase, setSelectedCase] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [evidence, setEvidence] = useState([])
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(Boolean(enabled))
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmStatusLoading, setLlmStatusLoading] = useState(false)
  const [error, setError] = useState(null)
  const [llmStatus, setLlmStatus] = useState(null)
  const [llmVerification, setLlmVerification] = useState(null)
  const [summaryOutput, setSummaryOutput] = useState(null)
  const [timelineSummary, setTimelineSummary] = useState(null)
  const [evidenceSummary, setEvidenceSummary] = useState(null)
  const [queryAnswer, setQueryAnswer] = useState(null)
  const [generatedReport, setGeneratedReport] = useState(null)
  const [filters, setFilters] = useState({ ...DEFAULT_FILTERS, ...initialFilters })
  const hasDataRef = useRef(false)

  const refresh = useCallback(async (overrides = {}) => {
    if (!enabled) {
      setLoading(false)
      return []
    }
    try {
      const activeFilters = { ...filters, ...overrides }
      const response = await listCases(activeFilters)
      setCases(response.items)
      setError(null)
      hasDataRef.current = true
      return response.items
    } catch (err) {
      setError(normalizeError(err))
      return []
    } finally {
      setLoading(false)
    }
  }, [enabled, filters])

  const loadCaseDetail = useCallback(async (caseId) => {
    if (!caseId) {
      setSelectedCase(null)
      setTimeline([])
      setEvidence([])
      setNotes([])
      setSummaryOutput(null)
      setTimelineSummary(null)
      setEvidenceSummary(null)
      setQueryAnswer(null)
      setGeneratedReport(null)
      return null
    }
    setDetailLoading(true)
    try {
      const [caseResponse, timelineResponse, evidenceResponse, notesResponse] = await Promise.all([
        getCase(caseId),
        getTimeline(caseId),
        listEvidence(caseId),
        listNotes(caseId),
      ])
      setSelectedCase(caseResponse.item)
      setTimeline(timelineResponse.items)
      setEvidence(evidenceResponse.items)
      setNotes(notesResponse.items)
      setSummaryOutput(null)
      setTimelineSummary(null)
      setEvidenceSummary(null)
      setQueryAnswer(null)
      setGeneratedReport(null)
      setError(null)
      return caseResponse.item
    } catch (err) {
      setError(normalizeError(err))
      return null
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    if (!enabled) return undefined
    const timer = window.setInterval(() => refresh(), pollMs)
    return () => window.clearInterval(timer)
  }, [enabled, pollMs, refresh])

  const loadLlmStatus = useCallback(async () => {
    if (!enabled) {
      setLlmStatus(null)
      return null
    }
    setLlmStatusLoading(true)
    try {
      const response = await getLlmStatus()
      setLlmStatus(response.item)
      setError(null)
      return response.item
    } catch (err) {
      setError(normalizeError(err))
      return null
    } finally {
      setLlmStatusLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    loadLlmStatus()
    if (!enabled) return undefined
    const timer = window.setInterval(() => loadLlmStatus(), Math.max(30000, pollMs))
    return () => window.clearInterval(timer)
  }, [enabled, loadLlmStatus, pollMs])

  const applyAction = useCallback(async (fn, { caseId, refreshDetail = true } = {}) => {
    setActionLoading(true)
    try {
      const response = await fn()
      await refresh()
      const targetId = caseId || response.item?.case_id || selectedCase?.case_id
      if (refreshDetail && targetId) {
        await loadCaseDetail(targetId)
      }
      setError(null)
      return response.item
    } catch (err) {
      setError(normalizeError(err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [loadCaseDetail, refresh, selectedCase?.case_id])

  const createManualCase = useCallback((payload) => applyAction(
    () => createCase(payload),
    { caseId: null, refreshDetail: false },
  ), [applyAction])

  const updateExistingCase = useCallback((caseId, payload) => applyAction(
    () => updateCase(caseId, payload),
    { caseId },
  ), [applyAction])

  const createFromEvent = useCallback((eventId) => applyAction(
    () => createCaseFromEvent(eventId),
    { caseId: null, refreshDetail: false },
  ), [applyAction])

  const addCaseEvidence = useCallback((caseId, payload) => applyAction(
    () => addEvidence(caseId, payload),
    { caseId },
  ), [applyAction])

  const addCaseNote = useCallback((caseId, payload) => applyAction(
    () => addNote(caseId, payload),
    { caseId },
  ), [applyAction])

  const assignSelectedCase = useCallback((caseId, assignedTo, reason = '') => applyAction(
    () => assignCase(caseId, assignedTo, reason),
    { caseId },
  ), [applyAction])

  const closeSelectedCase = useCallback((caseId, reason = '') => applyAction(
    () => closeCase(caseId, reason),
    { caseId },
  ), [applyAction])

  const reopenSelectedCase = useCallback((caseId, reason = '') => applyAction(
    () => reopenCase(caseId, reason),
    { caseId },
  ), [applyAction])

  const dismissSelectedCase = useCallback((caseId, reason = '') => applyAction(
    () => dismissCase(caseId, reason),
    { caseId },
  ), [applyAction])

  const archiveSelectedCase = useCallback((caseId, reason = '') => applyAction(
    () => archiveCase(caseId, reason),
    { caseId },
  ), [applyAction])

  const exportSelectedCase = useCallback(async (caseId, format = 'json') => {
    setActionLoading(true)
    try {
      const response = await exportCase(caseId, format)
      await loadCaseDetail(caseId)
      setError(null)
      return response.item
    } catch (err) {
      setError(normalizeError(err))
      throw err
    } finally {
      setActionLoading(false)
    }
  }, [loadCaseDetail])

  const applyLlmAction = useCallback(async (fn, { onSuccess } = {}) => {
    setLlmLoading(true)
    try {
      const response = await fn()
      if (onSuccess) onSuccess(response.item)
      await loadLlmStatus()
      setError(null)
      return response.item
    } catch (err) {
      setError(normalizeError(err))
      throw err
    } finally {
      setLlmLoading(false)
    }
  }, [loadLlmStatus])

  const verifyProvider = useCallback((payload = {}) => applyLlmAction(
    () => verifyLlmProvider(payload),
    { onSuccess: setLlmVerification },
  ), [applyLlmAction])

  const generateSummary = useCallback((caseId, payload = {}) => applyLlmAction(
    () => summarizeCase(caseId, payload),
    { onSuccess: setSummaryOutput },
  ), [applyLlmAction])

  const generateTimelineSummary = useCallback((caseId, payload = {}) => applyLlmAction(
    () => summarizeTimeline(caseId, payload),
    { onSuccess: setTimelineSummary },
  ), [applyLlmAction])

  const generateEvidenceSummary = useCallback((caseId, payload = {}) => applyLlmAction(
    () => summarizeEvidence(caseId, payload),
    { onSuccess: setEvidenceSummary },
  ), [applyLlmAction])

  const generateReport = useCallback((caseId, payload = {}) => applyLlmAction(
    () => draftCaseReport(caseId, payload),
    { onSuccess: setGeneratedReport },
  ), [applyLlmAction])

  const askQuery = useCallback((caseId, payload) => applyLlmAction(
    () => askCaseQuestion(caseId, payload),
    { onSuccess: setQueryAnswer },
  ), [applyLlmAction])

  const relatedCaseByEvent = useCallback((eventId) => {
    if (!eventId) return null
    return cases.find(item => (item.source_event_ids || []).includes(String(eventId))) || null
  }, [cases])

  const requiringReviewCount = useMemo(
    () => cases.filter(item => item.requires_review && item.review_status === 'pending').length,
    [cases],
  )

  const criticalCount = useMemo(
    () => cases.filter(item => item.priority === 'critical' || item.severity === 'critical').length,
    [cases],
  )

  const openCount = useMemo(
    () => cases.filter(item => ['open', 'investigating'].includes(item.status)).length,
    [cases],
  )

  return {
    cases,
    selectedCase,
    timeline,
    evidence,
    notes,
    loading,
    detailLoading,
    actionLoading,
    llmLoading,
    llmStatusLoading,
    error,
    llmStatus,
    llmVerification,
    summaryOutput,
    timelineSummary,
    evidenceSummary,
    queryAnswer,
    generatedReport,
    setGeneratedReport,
    filters,
    setFilters,
    refresh,
    loadLlmStatus,
    selectCase: loadCaseDetail,
    createCase: createManualCase,
    updateCase: updateExistingCase,
    createCaseFromEvent: createFromEvent,
    addEvidence: addCaseEvidence,
    addNote: addCaseNote,
    assignCase: assignSelectedCase,
    closeCase: closeSelectedCase,
    reopenCase: reopenSelectedCase,
    dismissCase: dismissSelectedCase,
    archiveCase: archiveSelectedCase,
    exportCase: exportSelectedCase,
    verifyLlmProvider: verifyProvider,
    generateCaseSummary: generateSummary,
    generateTimelineSummary,
    generateEvidenceSummary,
    generateReport,
    askCaseQuestion: askQuery,
    relatedCaseByEvent,
    requiringReviewCount,
    criticalCount,
    openCount,
    hasData: hasDataRef.current,
  }
}
