import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  acknowledgeAlert,
  escalateAlert,
  getAlert,
  getAlertHistory,
  getLiveAlerts,
  resolveAlert,
} from '../api/alertsApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { alertStore } from '../state/alertStore'
import { compareSeverity } from '../utils/severity'

export function useAlerts({ pollMs = DASHBOARD_POLL_MS, limit = 100 } = {}) {
  const [alerts, setAlerts] = useState([])
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [stale, setStale] = useState(false)
  const hasDataRef = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const response = await getLiveAlerts({ limit })
      setAlerts(response.items)
      alertStore.setAlerts(response.items)
      setError(null)
      setStale(false)
      setUpdatedAt(Date.now())
      hasDataRef.current = true
    } catch (err) {
      setError(normalizeError(err))
      setStale(hasDataRef.current)
    } finally {
      setLoading(false)
    }
  }, [limit])

  const selectAlert = useCallback(async alertId => {
    if (!alertId) {
      setSelectedAlert(null)
      setHistory([])
      alertStore.selectAlert(null)
      return
    }
    setDetailLoading(true)
    setActionError(null)
    alertStore.selectAlert(alertId)
    try {
      const [detail, historyResponse] = await Promise.all([getAlert(alertId), getAlertHistory(alertId)])
      setSelectedAlert(detail.item)
      setHistory(historyResponse.items)
      if (!detail.item) setActionError('Alert was not found')
    } catch (err) {
      setActionError(normalizeError(err))
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const runAction = useCallback(async (alertId, action, payload) => {
    setActionLoading(`${action}:${alertId}`)
    setActionError(null)
    try {
      const response =
        action === 'acknowledge'
          ? await acknowledgeAlert(alertId, payload?.operatorId)
          : action === 'resolve'
            ? await resolveAlert(alertId, payload?.operatorId)
            : await escalateAlert(alertId, payload?.reason)
      if (response.item) setSelectedAlert(response.item)
      await refresh()
      await selectAlert(alertId)
      return response.item
    } catch (err) {
      setActionError(normalizeError(err))
      return null
    } finally {
      setActionLoading(null)
    }
  }, [refresh, selectAlert])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(timer)
  }, [pollMs, refresh])

  const sortedAlerts = useMemo(() => (
    [...alerts].sort((a, b) => {
      const severityOrder = compareSeverity(a.severity, b.severity)
      if (severityOrder !== 0) return severityOrder
      return Number(b.updated_at || 0) - Number(a.updated_at || 0)
    })
  ), [alerts])

  return {
    alerts: sortedAlerts,
    selectedAlert,
    history,
    loading,
    detailLoading,
    actionLoading,
    error,
    actionError,
    stale,
    updatedAt,
    refresh,
    selectAlert,
    acknowledge: (alertId, operatorId) => runAction(alertId, 'acknowledge', { operatorId }),
    resolve: (alertId, operatorId) => runAction(alertId, 'resolve', { operatorId }),
    escalate: (alertId, reason) => runAction(alertId, 'escalate', { reason }),
  }
}
