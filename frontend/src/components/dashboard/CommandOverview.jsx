import { useState } from 'react'
import AlertFeed from './AlertFeed'
import CameraGrid from './CameraGrid'
import CameraDetailPanel from './CameraDetailPanel'
import CameraTimelinePanel from './CameraTimelinePanel'
import HeatmapPanel from './HeatmapPanel'
import LiveVideoSurface from './LiveVideoSurface'
import IncidentPanel from './IncidentPanel'
import MetricsPanel from './MetricsPanel'
import SystemHealthPanel from './SystemHealthPanel'
import TimelinePanel from './TimelinePanel'
import IncidentReplayDrawer from '../incidents/IncidentReplayDrawer'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

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
  // Metrics / health
  metricsState,
  health,
  websocketStatus,
  // Anomalies
  anomalies,
  anomaliesLoading,
  anomaliesError,
  onRefreshAnomalies,
}) {
  const [replayIncident, setReplayIncident] = useState(null)
  const [replayOpen, setReplayOpen] = useState(false)
  const [timelineFrame, setTimelineFrame] = useState(null)

  const selectedFrame = selectedCamera ? framesByCameraId[selectedCamera.camera_id] : null
  const selectedStreamSession = selectedCamera ? streamStatesByCameraId[selectedCamera.camera_id] : null

  function openReplay(incident) {
    setReplayIncident(incident)
    setReplayOpen(true)
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
            {selectedCamera && (
              <CameraDetailPanel
                camera={selectedCamera}
                onClose={null}
                relatedAlerts={selectedCameraAlerts}
              />
            )}
          </div>

          {/* Camera forensic timeline */}
          {selectedCamera && (
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
          {selectedCamera && (
            <HeatmapPanel defaultCameraId={selectedCamera.camera_id} />
          )}
          <RecentAnomalies
            anomalies={anomalies}
            loading={anomaliesLoading}
            error={anomaliesError}
            onRetry={onRefreshAnomalies}
          />
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

      <IncidentReplayDrawer
        open={replayOpen}
        incident={replayIncident}
        onClose={() => setReplayOpen(false)}
      />
    </>
  )
}

function RecentAnomalies({ anomalies = [], loading, error, onRetry }) {
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
            </li>
          ))}
        </ol>
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
