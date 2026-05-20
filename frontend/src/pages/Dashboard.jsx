import { useCallback, useEffect, useMemo, useState } from 'react'
import { getDashboardOverview } from '../api/analyticsApi'
import { getLiveAnomalies } from '../api/camerasApi'
import { normalizeError } from '../api/client'
import AlertDetailDrawer from '../components/alerts/AlertDetailDrawer'
import CaseDetailDrawer from '../components/cases/CaseDetailDrawer'
import OperationsTimeline from '../components/command/OperationsTimeline'
import ReviewQueuePanel from '../components/command/ReviewQueuePanel'
import Tactical3DStatusScene from '../components/command/Tactical3DStatusScene'
import CommandOverview from '../components/dashboard/CommandOverview'
import CommandPageHeader from '../components/layout/CommandPageHeader'
import { useCameras } from '../hooks/useCameras'
import { useAuth } from '../hooks/useAuth'
import { useLatestFrames } from '../hooks/useLatestFrames'
import { useFrameUpdates } from '../hooks/useFrameUpdates'
import { useHandoffs } from '../hooks/useHandoffs'
import { useWebSocketHandoffs } from '../hooks/useWebSocketHandoffs'
import { useMapState } from '../hooks/useMapState'
import { getStreams } from '../api/camerasApi'
import { compareSeverity } from '../utils/severity'
import { DASHBOARD_POLL_MS } from '../config'
import { useDroneSimulation } from '../hooks/useDroneSimulation'
import { useSimulationSources } from '../hooks/useSimulationSources'
import { useScenario } from '../hooks/useScenario'
import ExhibitionDemoPanel from '../components/exhibition/ExhibitionDemoPanel'

export default function Dashboard({ alertState, incidentState, caseState, metricsState, websocketState, health }) {
  const auth = useAuth()
  const authReady = Boolean(auth.ready ?? !auth.loading)
  const dashboardReady = authReady && auth.authenticated
  const canDroneRead = dashboardReady && auth.hasPermission('drone:read')
  const canSystemRead = dashboardReady && auth.hasPermission('system:read')
  const canMapRead = dashboardReady && auth.hasPermission('map:read')
  const canCameraRead = dashboardReady && auth.hasPermission('camera:read')
  const canStreamRead = dashboardReady && auth.hasPermission('stream:read')
  const canAlertRead = dashboardReady && auth.hasPermission('alert:read')
  const canAnalyticsRead = dashboardReady && auth.hasPermission('analytics:read')
  const drone = useDroneSimulation({ enabled: canDroneRead, pollMs: DASHBOARD_POLL_MS })
  const sim = useSimulationSources({ enabled: canSystemRead, pollMs: DASHBOARD_POLL_MS })
  const refreshSimulationSources = sim.refresh
  const scenario = useScenario({ enabled: canSystemRead })

  // Hash-based scroll: handles #exhibition-demo and #scenario-tracking/{runId}
  useEffect(() => {
    function handleHashChange() {
      const hash = window.location.hash
      if (hash === '#exhibition-demo') {
        const el = document.getElementById('exhibition-demo')
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        return
      }
      if (!hash.startsWith('#scenario-tracking/')) return
      const el = document.querySelector('[data-tracking-panel]')
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    window.addEventListener('hashchange', handleHashChange)
    handleHashChange()
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])
  const [anomalies, setAnomalies] = useState([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(true)
  const [anomaliesError, setAnomaliesError] = useState(null)
  const [analyticsPreview, setAnalyticsPreview] = useState(null)
  const [analyticsPreviewError, setAnalyticsPreviewError] = useState(null)

  const {
    mapState,
    loading: mapLoading,
    error: mapError,
    refresh: refreshMap,
    setSelectedCameraId: setMapSelectedCameraId,
  } = useMapState({ enabled: canMapRead, pollMs: DASHBOARD_POLL_MS })

  const {
    activeHandoffs: polledActiveHandoffs,
    recentHandoffs,
  } = useHandoffs({ enabled: canMapRead, pollMs: DASHBOARD_POLL_MS })

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
  const { cameras, loading: camerasLoading, error: camerasError, refresh: refreshCameras, selectedCamera, setSelectedCamera } = useCameras({ enabled: canCameraRead })
  const { framesByCameraId: polledFrames, refresh: refreshFrames } = useLatestFrames({ enabled: canCameraRead })
  const { framesByCameraId: wsFrames } = useFrameUpdates()
  // Merge WS frame updates (lower latency) with polling fallback
  const framesByCameraId = useMemo(
    () => ({ ...polledFrames, ...wsFrames }),
    [polledFrames, wsFrames],
  )
  const [streamStatesByCameraId, setStreamStatesByCameraId] = useState({})

  // Fetch stream session states
  const refreshStreamStates = useCallback(async () => {
    if (!canStreamRead) return {}
    try {
      const res = await getStreams()
      const byId = {}
      for (const s of res.items) {
        if (s?.camera_id) byId[s.camera_id] = s
      }
      setStreamStatesByCameraId(byId)
      return byId
    } catch {
      // Stream state is advisory on the dashboard; camera and alert panels still render without it.
      return {}
    }
  }, [canStreamRead])

  useEffect(() => {
    const load = () => { refreshStreamStates() }
    const initial = window.setTimeout(load, 0)
    if (!canStreamRead) return undefined
    const t = window.setInterval(refreshStreamStates, DASHBOARD_POLL_MS)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(t)
    }
  }, [canStreamRead, refreshStreamStates])

  const dashboardCameras = useMemo(
    () => (sim.cameras.length > 0 ? sim.cameras : cameras),
    [cameras, sim.cameras],
  )
  const dashboardCamerasLoading = sim.loading && dashboardCameras.length === 0 ? sim.loading : camerasLoading
  const dashboardCamerasError = sim.cameras.length > 0 ? sim.error : camerasError

  // Auto-select first camera when cameras load
  useEffect(() => {
    if (!selectedCamera && dashboardCameras.length > 0) {
      setSelectedCamera(dashboardCameras[0])
    }
  }, [dashboardCameras, selectedCamera, setSelectedCamera])

  const refreshAnomalies = useCallback(async () => {
    if (!canAlertRead) {
      setAnomaliesLoading(false)
      setAnomaliesError(null)
      setAnomalies([])
      return []
    }
    setAnomaliesLoading(true)
    try {
      const response = await getLiveAnomalies()
      setAnomalies(response.items)
      setAnomaliesError(null)
      return response.items
    } catch (err) {
      setAnomaliesError(normalizeError(err))
      return []
    } finally {
      setAnomaliesLoading(false)
    }
  }, [canAlertRead])

  useEffect(() => {
    const load = () => { refreshAnomalies() }
    const initial = window.setTimeout(load, 0)
    if (!canAlertRead) return undefined
    const timer = window.setInterval(refreshAnomalies, 15000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [canAlertRead, refreshAnomalies])

  const refreshAnalyticsPreview = useCallback(async () => {
    if (!canAnalyticsRead) {
      setAnalyticsPreviewError(null)
      return null
    }
    try {
      const response = await getDashboardOverview({ bucket: '1h' })
      setAnalyticsPreview(response.item)
      setAnalyticsPreviewError(null)
      return response.item
    } catch (err) {
      setAnalyticsPreviewError(normalizeError(err))
      return null
    }
  }, [canAnalyticsRead])

  useEffect(() => {
    const load = () => { refreshAnalyticsPreview() }
    const initial = window.setTimeout(load, 0)
    if (!canAnalyticsRead) return undefined
    const timer = window.setInterval(refreshAnalyticsPreview, 30000)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [canAnalyticsRead, refreshAnalyticsPreview])

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
    refreshSimulationSources()
  }, [refreshCameras, refreshFrames, refreshSimulationSources, refreshStreamStates])

  return (
    <>
      <CommandPageHeader
        eyebrow="Overview"
        title="Command Dashboard"
        description="Unified operational status across live streams, cases, map activity, simulated drone runtime, and operator review workflows."
        badges={[
          `${mergedAlerts.length} active alerts`,
          `${caseState?.requiringReviewCount || 0} cases require review`,
          `${activeHandoffs.length} active handoffs`,
        ]}
        actions={(
          <div className="button-row">
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'live-streams' }}>
              Open live streams
            </button>
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'drone-operations' }}>
              Open drone hub
            </button>
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'cases' }}>
              Open cases
            </button>
          </div>
        )}
      />

      <div className="command-summary-grid" style={{ marginBottom: 16 }}>
        <article className="command-summary-card">
          <span>Operational status</span>
          <strong>{health?.status || 'unknown'}</strong>
          <p>{health?.reasons?.[0] || 'Runtime telemetry is flowing through the dashboard.'}</p>
        </article>
        <article className="command-summary-card">
          <span>City surveillance network</span>
          <strong>{sim.cameras.length || cameras.length}</strong>
          <p>
            {sim.cameras.length > 0
              ? `${sim.cameras.length} simulated city camera${sim.cameras.length !== 1 ? 's' : ''} · ${sim.drones.length} drone${sim.drones.length !== 1 ? 's' : ''} registered`
              : `${analyticsPreview?.summary?.degraded_streams ?? 0} degraded stream(s) reported`}
          </p>
        </article>
        <article className="command-summary-card">
          <span>Drone status summary</span>
          <strong>{drone.status?.health?.status || 'unknown'}</strong>
          <p>{drone.telemetry?.timestamp ? `Latest simulated telemetry at ${drone.telemetry.timestamp}` : 'No simulated telemetry reported to the dashboard yet.'}</p>
        </article>
        <article className="command-summary-card">
          <span>Review queue</span>
          <strong>{caseState?.requiringReviewCount || 0}</strong>
          <p>Cases and cross-source observations remain operator-reviewed workflows.</p>
        </article>
        <article className="command-summary-card">
          <span>Uploaded-video intelligence</span>
          <strong>{analyticsPreview?.summary?.uploaded_video_alerts_generated ?? 0}</strong>
          <p>
            {(analyticsPreview?.summary?.uploaded_video_processed_videos ?? 0) > 0
              ? `${analyticsPreview.summary.uploaded_video_processed_videos} processed video(s), ${analyticsPreview.summary.uploaded_video_detection_count ?? 0} normalized event(s).`
              : 'No processed uploaded-video intelligence yet.'}
          </p>
        </article>
      </div>

      <div style={{ marginBottom: 16 }} id="exhibition-demo">
        <ExhibitionDemoPanel />
      </div>

      <div className="command-two-column" style={{ marginBottom: 16 }}>
        <Tactical3DStatusScene summary="Abstract overview of cameras, simulated drone runtime, and fusion dependencies for the FYP command-center demo." />
        <ReviewQueuePanel limit={8} />
      </div>

      <div style={{ marginBottom: 16 }}>
        <OperationsTimeline />
      </div>

      <section className="panel analytics-preview-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Analytics Preview</p>
            <h2>Supervisor Snapshot</h2>
          </div>
          <div className="button-row">
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'exhibition-demo'; document.getElementById('exhibition-demo')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}>
              Exhibition Demo
            </button>
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'analytics' }}>
              Open Analytics
            </button>
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'uploaded-video-analysis' }}>
              Analyze Video
            </button>
            {auth.hasPermission('gis:read') ? (
              <button type="button" className="text-button" onClick={() => { window.location.hash = 'map-operations' }}>
                View on Map
              </button>
            ) : null}
            {auth.hasPermission('drone:read') ? (
              <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-simulation' }}>
                Drone Simulation
              </button>
            ) : null}
          </div>
        </div>
        {analyticsPreviewError ? <p className="muted">{analyticsPreviewError}</p> : null}
        <div className="metric-strip">
          <article className="metric-tile"><span>Highest-risk camera</span><strong>{analyticsPreview?.risk?.highest_risk_camera || 'N/A'}</strong></article>
          <article className="metric-tile"><span>Critical events 24h</span><strong>{analyticsPreview?.summary?.critical_events ?? 0}</strong></article>
          <article className="metric-tile"><span>Cases requiring review</span><strong>{analyticsPreview?.summary?.cases_requiring_review ?? 0}</strong></article>
          <article className="metric-tile"><span>Degraded streams</span><strong>{analyticsPreview?.summary?.degraded_streams ?? 0}</strong></article>
        </div>
        <div className="metric-strip" style={{ marginTop: 12 }}>
          <article className="metric-tile"><span>Processed videos</span><strong>{analyticsPreview?.summary?.uploaded_video_processed_videos ?? 0}</strong></article>
          <article className="metric-tile"><span>Upload alerts</span><strong>{analyticsPreview?.summary?.uploaded_video_alerts_generated ?? 0}</strong></article>
          <article className="metric-tile"><span>Severe upload detections</span><strong>{analyticsPreview?.summary?.uploaded_video_high_severity_detections ?? 0}</strong></article>
          <article className="metric-tile"><span>Upload evidence refs</span><strong>{analyticsPreview?.summary?.uploaded_video_evidence_artifacts_created ?? 0}</strong></article>
        </div>
        {auth.hasPermission('drone:read') ? (
          <div className="metric-strip" style={{ marginTop: 12 }}>
            <article className="metric-tile"><span>Drone status</span><strong>{drone.status?.health?.status || 'unknown'}</strong></article>
            <article className="metric-tile"><span>Last telemetry</span><strong>{drone.telemetry?.timestamp || 'n/a'}</strong></article>
            <article className="metric-tile"><span>Frame processing</span><strong>{drone.stats.framesProcessed}</strong></article>
            <article className="metric-tile"><span>Drone events</span><strong>{drone.stats.events}</strong></article>
          </div>
        ) : null}
      </section>
      <CommandOverview
        // Camera props
        cameras={dashboardCameras}
        camerasLoading={dashboardCamerasLoading}
        camerasError={dashboardCamerasError}
        selectedCamera={selectedCamera}
        framesByCameraId={framesByCameraId}
        streamStatesByCameraId={streamStatesByCameraId}
        alertCountByCameraId={alertCountByCameraId}
        selectedCameraAlerts={selectedCameraAlerts}
        onCameraSelect={handleCameraSelect}
        onCameraRefresh={handleCameraRefresh}
        // Simulation source network
        simCameras={[]}
        simDrones={sim.drones}
        simLoading={sim.loading}
        simError={sim.error}
        onSimRefresh={sim.refresh}
        // Scenario engine (Phase 6)
        scenario={scenario}
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
        onUploadEvidenceFile={formData => caseState?.uploadEvidenceFile(caseState.selectedCase.case_id, formData)}
        onVerifyEvidenceFile={evidenceId => caseState?.verifyEvidenceFile(caseState.selectedCase.case_id, evidenceId)}
        onDownloadEvidenceFile={evidenceId => caseState?.downloadEvidenceFile(caseState.selectedCase.case_id, evidenceId)}
        onExportEvidenceManifest={() => caseState?.exportEvidenceManifest(caseState.selectedCase.case_id)}
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
