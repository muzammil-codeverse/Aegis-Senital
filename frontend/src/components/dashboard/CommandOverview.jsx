import { useState } from 'react'
import AlertFeed from './AlertFeed'
import CameraGrid from './CameraGrid'
import CameraDetailPanel from './CameraDetailPanel'
import CameraTimelinePanel from './CameraTimelinePanel'
import CrossCameraPanel from './CrossCameraPanel'
import HeatmapPanel from './HeatmapPanel'
import LiveVideoSurface from './LiveVideoSurface'
import IncidentPanel from './IncidentPanel'
import MetricsPanel from './MetricsPanel'
import OperationsMapPanel from './OperationsMapPanel'
import SystemHealthPanel from './SystemHealthPanel'
import TimelinePanel from './TimelinePanel'
import IncidentReplayDrawer from '../incidents/IncidentReplayDrawer'
import LiveStreamPanel from '../streaming/LiveStreamPanel'
import ScenarioControlPanel from '../simulation/ScenarioControlPanel'
import OperationalTrackingPanel from '../simulation/OperationalTrackingPanel'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

const DRONE_STATUS_COLOR = {
  standby: '#52c41a',
  airborne: '#1890ff',
  returning: '#fa8c16',
  charging: '#faad14',
  offline: '#8c8c8c',
  mission: '#1890ff',
}

const ROUTE_STATUS_COLOR = {
  dispatched: '#1890ff',
  tracking: '#52c41a',
  completed: '#6b7280',
  cancelled: '#ff4d4f',
  planned: '#faad14',
}

function DroneSummaryPanel({ drones = [], unifiedFleet = null }) {
  if (drones.length === 0) return null

  // Build a lookup: drone_id → unified state
  const unifiedByDroneId = {}
  if (unifiedFleet?.drones) {
    for (const ud of unifiedFleet.drones) {
      unifiedByDroneId[ud.drone_id] = ud
    }
  }

  return (
    <section className="panel" style={{ marginBottom: 8 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Surveillance Drones</p>
          <h2>City Drone Fleet</h2>
        </div>
        <span className="count-pill">{drones.length}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {drones.map(drone => {
          const ud = unifiedByDroneId[drone.drone_id]
          const routeStatus = ud?.route_status
          const hasActiveRoute = routeStatus && routeStatus !== 'none'
          const runId = ud?.active_scenario_run_id
          return (
            <div key={drone.drone_id} style={{
              display: 'flex', alignItems: 'flex-start', gap: 8,
              padding: '6px 8px', borderRadius: 4,
              background: 'rgba(255,255,255,0.03)',
              border: `1px solid ${hasActiveRoute ? 'rgba(24,144,255,0.2)' : 'rgba(255,255,255,0.07)'}`,
            }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 4,
                background: DRONE_STATUS_COLOR[drone.status] || '#8c8c8c',
              }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <strong style={{ fontSize: '0.78rem' }}>{drone.name}</strong>
                  <span style={{ fontSize: '0.6rem', color: '#6b7280' }}>{drone.drone_id}</span>
                  {hasActiveRoute && (
                    <span style={{ fontSize: '0.58rem', color: ROUTE_STATUS_COLOR[routeStatus] || '#1890ff', fontWeight: 600 }}>
                      {routeStatus.toUpperCase()}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '0.65rem', color: '#6b7280', marginTop: 1, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ color: DRONE_STATUS_COLOR[drone.status] || '#8c8c8c' }}>{drone.status}</span>
                  <span>Zone: <strong style={{ color: '#d1d5db' }}>{drone.assigned_zone}</strong></span>
                  {drone.battery_percent != null && (
                    <span>Battery: <strong style={{ color: drone.battery_percent < 30 ? '#ff4d4f' : '#52c41a' }}>{Math.round(drone.battery_percent)}%</strong></span>
                  )}
                </div>
                {ud?.linked_actor_id && (
                  <div style={{ fontSize: '0.6rem', color: '#fa8c16', marginTop: 1 }}>
                    Tracking: {ud.linked_actor_id}
                    {runId && (
                      <button
                        type="button"
                        onClick={() => { window.location.hash = `scenario-tracking/${runId}` }}
                        style={{
                          marginLeft: 8, fontSize: '0.55rem', color: '#1890ff',
                          background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline',
                        }}
                      >
                        View Tracking
                      </button>
                    )}
                  </div>
                )}
                {drone.capabilities?.length > 0 && (
                  <div style={{ fontSize: '0.58rem', color: '#4b5563', marginTop: 2 }}>
                    {drone.capabilities.slice(0, 3).join(' · ')}{drone.capabilities.length > 3 ? ` +${drone.capabilities.length - 3}` : ''}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export default function CommandOverview({
  // Camera props
  cameras = [],
  camerasLoading,
  camerasError,
  selectedCamera,
  framesByCameraId = {},
  streamStatesByCameraId = {},
  alertCountByCameraId = {},
  selectedCameraAlerts = [],
  onCameraSelect,
  onCameraRefresh,
  // Alert props
  alerts,
  alertState,
  // Incident props
  incidents,
  incidentState,
  caseState,
  // Metrics / health
  metricsState,
  health,
  websocketStatus,
  // Anomalies
  anomalies,
  anomaliesLoading,
  anomaliesError,
  onRefreshAnomalies,
  // Map
  mapState,
  mapLoading,
  mapError,
  onMapRefresh,
  // Handoffs
  activeHandoffs = [],
  recentHandoffs = [],
  handoffWsStatus = 'disconnected',
  // Simulation source network (Phase 5)
  simCameras = [],
  simDrones = [],
  simLoading = false,
  simError = null,
  onSimRefresh,
  // Scenario engine (Phase 6)
  scenario = null,
  // Unified drone fleet (Phase 8)
  unifiedFleet = null,
}) {
  const [replayIncident, setReplayIncident] = useState(null)
  const [replayOpen, setReplayOpen] = useState(false)
  const [timelineFrame, setTimelineFrame] = useState(null)

  const selectedFrame = selectedCamera ? framesByCameraId[selectedCamera.camera_id] : null
  const selectedStreamSession = selectedCamera ? streamStatesByCameraId[selectedCamera.camera_id] : null
  const selectedCameraIsSimulated = Boolean(selectedCamera?.simulated)

  function openReplay(incident) {
    setReplayIncident(incident)
    setReplayOpen(true)
  }

  function handleMapCameraSelect(camNode) {
    // Find the full Camera object from the camera list
    const cam = cameras.find(c => c.camera_id === camNode.camera_id)
    if (cam) onCameraSelect && onCameraSelect(cam)
  }

  return (
    <>
      <div className="command-grid command-grid--camera-console">
        {/* LEFT: Camera Grid */}
        <div className="grid-left">
          <CameraGrid
            cameras={cameras}
            framesByCameraId={framesByCameraId}
            streamStatesByCameraId={streamStatesByCameraId}
            alertCountByCameraId={alertCountByCameraId}
            selectedCameraId={selectedCamera?.camera_id}
            onCameraSelect={onCameraSelect}
            loading={camerasLoading}
            error={camerasError}
            onRefresh={onCameraRefresh}
          />
        </div>

        {/* CENTER: Live Video + Incidents + Timeline */}
        <div className="grid-center">
          {/* Live video surface for selected camera */}
          <div style={{ display: 'flex', gap: 8, flex: '0 0 auto' }}>
            <LiveVideoSurface
              camera={selectedCamera}
              latestFrame={selectedFrame}
              streamSession={selectedStreamSession}
              replayFrame={timelineFrame}
              selected
              onSelect={onCameraSelect}
            />
            {selectedCamera && !selectedCameraIsSimulated && (
              <CameraDetailPanel
                camera={selectedCamera}
                onClose={null}
                relatedAlerts={selectedCameraAlerts}
              />
            )}
          </div>

          {selectedCamera && !selectedCameraIsSimulated && (
            <LiveStreamPanel camera={selectedCamera} />
          )}

          {/* Operations map */}
          <OperationsMapPanel
            mapState={mapState}
            loading={mapLoading}
            error={mapError}
            onRefresh={onMapRefresh}
            selectedCameraId={selectedCamera?.camera_id}
            onCameraSelect={handleMapCameraSelect}
            onIncidentSelect={inc => openReplay({ incident_id: inc.incident_id, incident_type: inc.incident_type, severity: inc.severity })}
            activeHandoffs={activeHandoffs}
          />

          {/* Camera forensic timeline */}
          {selectedCamera && !selectedCameraIsSimulated && (
            <CameraTimelinePanel
              cameraId={selectedCamera.camera_id}
              onSelectFrame={frame => setTimelineFrame(frame)}
            />
          )}

          <IncidentPanel
            incidents={incidents}
            selectedIncident={incidentState.selectedIncident}
            selectedIncidentId={incidentState.selectedIncident?.incident_id || incidentState.selectedIncident?.id}
            loading={incidentState.loading}
            detailLoading={incidentState.detailLoading}
            error={incidentState.error}
            detailError={incidentState.detailError}
            stale={incidentState.stale}
            onRetry={incidentState.refresh}
            onSelect={incidentState.selectIncident}
            onReplay={openReplay}
          />
          <TimelinePanel defaultTrackId={firstTrackId(alerts, incidents)} />
        </div>

        {/* RIGHT: Alerts + Health + Heatmap + Anomalies */}
        <div className="grid-right">
          <AlertFeed
            alerts={alerts}
            loading={alertState.loading}
            error={alertState.error}
            stale={alertState.stale}
            selectedAlertId={alertState.selectedAlert?.alert_id}
            actionError={alertState.actionError}
            onRetry={alertState.refresh}
            onSelect={alertState.selectAlert}
            onAcknowledge={alertState.acknowledge}
            onResolve={alertState.resolve}
            onEscalate={alertState.escalate}
            busy={alertState.actionLoading}
          />
          <SystemHealthPanel
            health={health}
            metrics={metricsState.metrics}
            error={metricsState.error}
            websocketStatus={websocketStatus}
          />
          {selectedCamera && !selectedCameraIsSimulated && (
            <HeatmapPanel defaultCameraId={selectedCamera.camera_id} />
          )}
          <RecentAnomalies
            anomalies={anomalies}
            loading={anomaliesLoading}
            error={anomaliesError}
            onRetry={onRefreshAnomalies}
            caseState={caseState}
          />
          <RecentCasesPanel caseState={caseState} health={health} />
          <CrossCameraPanel
            activeHandoffs={activeHandoffs}
            recentHandoffs={recentHandoffs}
            wsStatus={handoffWsStatus}
          />
          {/* Drone fleet summary (Phase 5) */}
          <DroneSummaryPanel drones={simDrones} unifiedFleet={unifiedFleet} />
          {/* Crime scenario engine (Phase 6) */}
          {scenario && (
            <ScenarioControlPanel
              scenarios={scenario.scenarios}
              activeRun={scenario.activeRun}
              timeline={scenario.timeline}
              loading={scenario.loading}
              error={scenario.error}
              actionLoading={scenario.actionLoading}
              actionError={scenario.actionError}
              onStart={scenario.start}
              onStep={scenario.step}
              onPause={scenario.pause}
              onResume={scenario.resume}
              onCancel={scenario.cancel}
              onReset={scenario.reset}
            />
          )}
          {/* Phase 7 — Operational Tracking: suspect path, handoffs, drone route, fused track */}
          {scenario && (
            <div data-tracking-panel>
              <OperationalTrackingPanel activeRun={scenario.activeRun} />
            </div>
          )}
        </div>

        {/* BOTTOM: Metrics */}
        <div className="grid-bottom">
          <MetricsPanel
            metrics={metricsState.metrics}
            loading={metricsState.loading}
            error={metricsState.error}
            stale={metricsState.stale}
            onRetry={metricsState.refresh}
          />
        </div>
      </div>

      {/* Simulation City Surveillance Network (Phase 5) */}
      {(simCameras.length > 0 || simLoading) && (
        <div style={{ marginTop: 16 }}>
          <CameraGrid
            cameras={simCameras}
            framesByCameraId={{}}
            streamStatesByCameraId={{}}
            alertCountByCameraId={alertCountByCameraId}
            selectedCameraId={selectedCamera?.camera_id}
            onCameraSelect={onCameraSelect}
            loading={simLoading}
            error={simError}
            onRefresh={onSimRefresh}
            eyebrow="Simulated City CCTV"
            title="City Surveillance Network"
          />
        </div>
      )}

      <IncidentReplayDrawer
        open={replayOpen}
        incident={replayIncident}
        onClose={() => setReplayOpen(false)}
      />
    </>
  )
}

function RecentAnomalies({ anomalies = [], loading, error, onRetry, caseState }) {
  return (
    <section className="panel anomalies-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Behavioral Intelligence</p>
          <h2>Recent Anomalies</h2>
        </div>
        <span className="count-pill">{anomalies.length}</span>
      </div>
      {loading && <LoadingState label="Loading anomalies" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && anomalies.length === 0 && <EmptyState message="No live anomalies reported." />}
      {anomalies.length > 0 && (
        <ol className="timeline-list">
          {anomalies.slice(0, 6).map((anomaly, index) => (
            <li key={anomaly.anomaly_id || `${anomaly.timestamp}-${index}`}>
              <span>{formatTimestamp(anomaly.timestamp)}</span>
              <strong>{anomaly.anomaly_type || anomaly.type || 'anomaly'}</strong>
              <em>{formatPercent(anomaly.score || anomaly.risk_score)}</em>
              <div className="button-row">
                {caseState?.relatedCaseByEvent?.(anomaly.window_id || anomaly.anomaly_id) ? (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => caseState.selectCase(caseState.relatedCaseByEvent(anomaly.window_id || anomaly.anomaly_id).case_id)}
                  >
                    View Case
                  </button>
                ) : (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      const sourceId = anomaly.window_id || anomaly.anomaly_id
                      if (!sourceId) return
                      caseState?.createCaseFromEvent?.(sourceId).then(created => {
                        if (created?.case_id) caseState.selectCase(created.case_id)
                      }).catch(() => {})
                    }}
                  >
                    Create Case
                  </button>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function RecentCasesPanel({ caseState, health }) {
  const items = caseState?.cases?.slice(0, 5) || []
  const caseHealth = health?.case_management || health?.checks?.case_management || {}
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Case Management</p>
          <h2>Recent Cases</h2>
        </div>
        <span className="count-pill">{caseState?.cases?.length || 0}</span>
      </div>
      <div className="metric-strip case-metric-strip">
        <article className="metric-tile"><span>Open</span><strong>{caseState?.openCount || 0}</strong></article>
        <article className="metric-tile"><span>Critical</span><strong>{caseState?.criticalCount || 0}</strong></article>
        <article className="metric-tile"><span>Review</span><strong>{caseState?.requiringReviewCount || 0}</strong></article>
      </div>
      <div className="health-grid case-health-grid">
        <span>Status</span><strong>{caseHealth.status || 'unknown'}</strong>
        <span>Storage</span><strong>{caseHealth.storage || 'unknown'}</strong>
        <span>Open Cases</span><strong>{caseHealth.open_case_count ?? 0}</strong>
      </div>
      {items.length === 0 ? (
        <EmptyState message="No recent cases available." />
      ) : (
        <div className="stack-list">
          {items.map(item => (
            <article key={item.case_id} className="case-subcard">
              <div className="alert-card-header">
                <strong>{item.title || item.case_id}</strong>
                <span className="state-chip">{item.status}</span>
              </div>
              <p className="drawer-description">{item.description || 'Possible incident requires operator review.'}</p>
              <button type="button" className="text-button" onClick={() => caseState?.selectCase?.(item.case_id)}>View Case</button>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function firstTrackId(alerts, incidents) {
  const alertTrack = alerts?.find(a => Array.isArray(a.track_ids) && a.track_ids.length > 0)?.track_ids?.[0]
  if (alertTrack !== undefined) return String(alertTrack)
  const incidentTrack = incidents?.find(i => Array.isArray(i.track_ids) && i.track_ids.length > 0)?.track_ids?.[0]
  return incidentTrack !== undefined ? String(incidentTrack) : ''
}
