import { useCallback, useEffect, useMemo, useState } from 'react'
import { getLiveAnomalies } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import AlertDetailDrawer from '../components/alerts/AlertDetailDrawer'
import CaseDetailDrawer from '../components/cases/CaseDetailDrawer'
import CommandOverview from '../components/dashboard/CommandOverview'
import { useCameras } from '../hooks/useCameras'
import { useLatestFrames } from '../hooks/useLatestFrames'
import { useFrameUpdates } from '../hooks/useFrameUpdates'
import { useHandoffs } from '../hooks/useHandoffs'
import { useWebSocketHandoffs } from '../hooks/useWebSocketHandoffs'
import { useMapState } from '../hooks/useMapState'
import { getStreams } from '../api/camerasApi'
import { compareSeverity } from '../utils/severity'
import { DASHBOARD_POLL_MS } from '../config'

export default function Dashboard({ alertState, incidentState, caseState, metricsState, websocketState, health }) {
  const [anomalies, setAnomalies] = useState([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(true)
  const [anomaliesError, setAnomaliesError] = useState(null)

  const {
    mapState,
    loading: mapLoading,
    error: mapError,
    refresh: refreshMap,
    setSelectedCameraId: setMapSelectedCameraId,
  } = useMapState({ pollMs: DASHBOARD_POLL_MS })

  const {
    activeHandoffs: polledActiveHandoffs,
    recentHandoffs,
    mergeWebSocketHandoff,
  } = useHandoffs({ pollMs: DASHBOARD_POLL_MS })

  const { handoffList: wsHandoffList, status: handoffWsStatus } = useWebSocketHandoffs()

  // Merge WS handoff updates with polling
  const activeHandoffs = useMemo(() => {
    const byId = {}
    for (const h of polledActiveHandoffs) byId[h.handoff_id] = h
    for (const h of wsHandoffList) {
      if (h.state && h.state !== 'confirmed' && h.state !== 'rejected' && h.state !== 'expired') {
        byId[h.handoff_id] = { ...(byId[h.handoff_id] ?? {}), ...h }
      }
    }
    return Object.values(byId)
  }, [polledActiveHandoffs, wsHandoffList])

  // Camera state — managed here, passed down to avoid duplicate fetching
  const { cameras, loading: camerasLoading, error: camerasError, refresh: refreshCameras, selectedCamera, setSelectedCamera } = useCameras()
  const { framesByCameraId: polledFrames, refresh: refreshFrames } = useLatestFrames()
  const { framesByCameraId: wsFrames } = useFrameUpdates()
  // Merge WS frame updates (lower latency) with polling fallback
  const framesByCameraId = useMemo(
    () => ({ ...polledFrames, ...wsFrames }),
    [polledFrames, wsFrames],
  )
  const [streamStatesByCameraId, setStreamStatesByCameraId] = useState({})

  // Fetch stream session states
  const refreshStreamStates = useCallback(async () => {
    try {
      const res = await getStreams()
      const byId = {}
      for (const s of res.items) {
        if (s?.camera_id) byId[s.camera_id] = s
      }
      setStreamStatesByCameraId(byId)
    } catch (_) {}
  }, [])

  useEffect(() => {
    refreshStreamStates()
    const t = window.setInterval(refreshStreamStates, DASHBOARD_POLL_MS)
    return () => window.clearInterval(t)
  }, [refreshStreamStates])

  // Auto-select first camera when cameras load
  useEffect(() => {
    if (!selectedCamera && cameras.length > 0) {
      setSelectedCamera(cameras[0])
    }
  }, [cameras, selectedCamera, setSelectedCamera])

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
  const selectedAlertEventId = alertState.selectedAlert?.event_ids?.[0]
  const relatedCase = useMemo(
    () => caseState?.relatedCaseByEvent?.(selectedAlertEventId) || null,
    [caseState, selectedAlertEventId],
  )

  // Alert count per camera_id
  const alertCountByCameraId = useMemo(() => {
    const counts = {}
    mergedAlerts.forEach(alert => {
      ;(alert.camera_ids || []).forEach(cid => {
        counts[String(cid)] = (counts[String(cid)] || 0) + 1
      })
    })
    return counts
  }, [mergedAlerts])

  // Related alerts for selected camera
  const selectedCameraAlerts = useMemo(() => {
    if (!selectedCamera) return []
    return mergedAlerts.filter(a => (a.camera_ids || []).includes(selectedCamera.camera_id))
  }, [mergedAlerts, selectedCamera])

  const handleCameraSelect = useCallback(cam => {
    setSelectedCamera(cam)
    setMapSelectedCameraId(cam?.camera_id || null)
  }, [setSelectedCamera, setMapSelectedCameraId])

  const handleCameraRefresh = useCallback(() => {
    refreshCameras()
    refreshFrames()
    refreshStreamStates()
  }, [refreshCameras, refreshFrames, refreshStreamStates])

  return (
    <>
      <CommandOverview
        // Camera props
        cameras={cameras}
        camerasLoading={camerasLoading}
        camerasError={camerasError}
        selectedCamera={selectedCamera}
        framesByCameraId={framesByCameraId}
        streamStatesByCameraId={streamStatesByCameraId}
        alertCountByCameraId={alertCountByCameraId}
        selectedCameraAlerts={selectedCameraAlerts}
        onCameraSelect={handleCameraSelect}
        onCameraRefresh={handleCameraRefresh}
        // Alert props
        alerts={mergedAlerts}
        alertState={alertState}
        // Incident props
        incidents={incidentState.incidents}
        incidentState={incidentState}
        caseState={caseState}
        // Metrics / health
        metricsState={metricsState}
        health={health}
        websocketStatus={websocketState.status}
        // Anomalies
        anomalies={anomalies}
        anomaliesLoading={anomaliesLoading}
        anomaliesError={anomaliesError}
        onRefreshAnomalies={refreshAnomalies}
        // Map
        mapState={mapState}
        mapLoading={mapLoading}
        mapError={mapError}
        onMapRefresh={refreshMap}
        // Handoffs
        activeHandoffs={activeHandoffs}
        recentHandoffs={recentHandoffs}
        handoffWsStatus={handoffWsStatus}
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
        relatedCase={relatedCase}
        onViewCase={() => relatedCase && caseState.selectCase(relatedCase.case_id)}
        onCreateCaseFromEvent={() => {
          if (!selectedAlertEventId) return
          caseState.createCaseFromEvent(selectedAlertEventId).then(created => {
            if (created?.case_id) caseState.selectCase(created.case_id)
          }).catch(() => {})
        }}
        caseBusy={caseState?.actionLoading}
      />
      <CaseDetailDrawer
        open={Boolean(caseState?.selectedCase)}
        caseItem={caseState?.selectedCase}
        loading={caseState?.detailLoading}
        error={caseState?.error}
        timeline={caseState?.timeline}
        evidence={caseState?.evidence}
        notes={caseState?.notes}
        busy={caseState?.actionLoading}
        onClose={() => caseState?.selectCase(null)}
        onAssign={(assignedTo, reason) => caseState?.assignCase(caseState.selectedCase.case_id, assignedTo, reason)}
        onAddEvidence={payload => caseState?.addEvidence(caseState.selectedCase.case_id, payload)}
        onAddNote={payload => caseState?.addNote(caseState.selectedCase.case_id, payload)}
        onResolve={reason => caseState?.closeCase(caseState.selectedCase.case_id, reason)}
        onReopen={reason => caseState?.reopenCase(caseState.selectedCase.case_id, reason)}
        onDismiss={reason => caseState?.dismissCase(caseState.selectedCase.case_id, reason)}
        onArchive={reason => caseState?.archiveCase(caseState.selectedCase.case_id, reason)}
        onExport={format => caseState?.exportCase(caseState.selectedCase.case_id, format)}
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
    const sev = compareSeverity(a.severity, b.severity)
    if (sev !== 0) return sev
    return Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0)
  })
}
