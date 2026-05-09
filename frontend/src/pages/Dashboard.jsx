import { useCallback, useEffect, useMemo, useState } from 'react'
import { getLiveAnomalies } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import AlertDetailDrawer from '../components/alerts/AlertDetailDrawer'
import CommandOverview from '../components/dashboard/CommandOverview'
import { compareSeverity, normalizeSeverity } from '../utils/severity'

export default function Dashboard({ alertState, incidentState, metricsState, websocketState, health }) {
  const [anomalies, setAnomalies] = useState([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(true)
  const [anomaliesError, setAnomaliesError] = useState(null)

  const refreshAnomalies = useCallback(async () => {
    setAnomaliesLoading(true)
    try {
      const response = await getLiveAnomalies()
      setAnomalies(response.items)
      setAnomaliesError(null)
    } catch (err) {
      setAnomaliesError(normalizeError(err))
    } finally {
      setAnomaliesLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshAnomalies()
    const timer = window.setInterval(refreshAnomalies, 15000)
    return () => window.clearInterval(timer)
  }, [refreshAnomalies])

  const mergedAlerts = useMemo(() => mergeAlerts(alertState.alerts, websocketState.alerts), [alertState.alerts, websocketState.alerts])
  const cameras = useMemo(() => deriveCameraSummaries(mergedAlerts, incidentState.incidents), [mergedAlerts, incidentState.incidents])

  return (
    <>
      <CommandOverview
        alerts={mergedAlerts}
        alertState={alertState}
        incidents={incidentState.incidents}
        incidentState={incidentState}
        metricsState={metricsState}
        health={health}
        websocketStatus={websocketState.status}
        cameras={cameras}
        anomalies={anomalies}
        anomaliesLoading={anomaliesLoading}
        anomaliesError={anomaliesError}
        onRefreshAnomalies={refreshAnomalies}
      />
      <AlertDetailDrawer
        open={Boolean(alertState.selectedAlert)}
        alert={alertState.selectedAlert}
        history={alertState.history}
        loading={alertState.detailLoading}
        error={alertState.actionError}
        onClose={() => alertState.selectAlert(null)}
        onAcknowledge={alertState.acknowledge}
        onResolve={alertState.resolve}
        onEscalate={alertState.escalate}
        busy={alertState.actionLoading}
      />
    </>
  )
}

function mergeAlerts(apiAlerts, websocketAlerts) {
  const byId = new Map()
  ;[...apiAlerts, ...websocketAlerts].forEach(alert => {
    if (!alert?.alert_id) return
    byId.set(alert.alert_id, { ...byId.get(alert.alert_id), ...alert })
  })
  return [...byId.values()].sort((a, b) => {
    const severityOrder = compareSeverity(a.severity, b.severity)
    if (severityOrder !== 0) return severityOrder
    return Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0)
  })
}

function deriveCameraSummaries(alerts, incidents) {
  const cameras = new Map()
  function ensure(cameraId) {
    if (!cameras.has(cameraId)) {
      cameras.set(cameraId, {
        camera_id: cameraId,
        status: 'referenced',
        eventCount: 0,
        riskScore: 0,
        riskSeverity: 'info',
        track_ids: [],
      })
    }
    return cameras.get(cameraId)
  }
  alerts.forEach(alert => {
    ;(alert.camera_ids || []).forEach(cameraId => {
      const camera = ensure(String(cameraId))
      camera.eventCount += 1
      camera.riskScore = Math.max(camera.riskScore, Number(alert.risk_score || 0))
      camera.riskSeverity = higherSeverity(camera.riskSeverity, alert.severity)
      camera.track_ids = [...new Set([...camera.track_ids, ...(alert.track_ids || [])])]
    })
  })
  incidents.forEach(incident => {
    ;(incident.camera_ids || []).forEach(cameraId => {
      const camera = ensure(String(cameraId))
      camera.eventCount += 1
      camera.riskScore = Math.max(camera.riskScore, Number(incident.risk_score || 0))
      camera.riskSeverity = higherSeverity(camera.riskSeverity, incident.severity)
      camera.track_ids = [...new Set([...camera.track_ids, ...(incident.track_ids || [])])]
    })
  })
  return [...cameras.values()]
}

function higherSeverity(current, incoming) {
  return compareSeverity(incoming, current) < 0 ? normalizeSeverity(incoming) : normalizeSeverity(current)
}
