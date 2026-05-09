import AlertFeed from './AlertFeed'
import CameraGrid from './CameraGrid'
import IncidentPanel from './IncidentPanel'
import MetricsPanel from './MetricsPanel'
import SystemHealthPanel from './SystemHealthPanel'
import TimelinePanel from './TimelinePanel'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

export default function CommandOverview({
  alerts,
  alertState,
  incidents,
  incidentState,
  metricsState,
  health,
  websocketStatus,
  cameras,
  anomalies,
  anomaliesLoading,
  anomaliesError,
  onRefreshAnomalies,
}) {
  return (
    <div className="command-grid">
      <div className="grid-left">
        <CameraGrid cameras={cameras} />
      </div>
      <div className="grid-center">
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
        />
        <TimelinePanel defaultTrackId={firstTrackId(alerts, incidents)} />
      </div>
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
        <RecentAnomalies
          anomalies={anomalies}
          loading={anomaliesLoading}
          error={anomaliesError}
          onRetry={onRefreshAnomalies}
        />
      </div>
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
  const alertTrack = alerts.find(alert => Array.isArray(alert.track_ids) && alert.track_ids.length > 0)?.track_ids?.[0]
  if (alertTrack !== undefined) return String(alertTrack)
  const incidentTrack = incidents.find(incident => Array.isArray(incident.track_ids) && incident.track_ids.length > 0)?.track_ids?.[0]
  return incidentTrack !== undefined ? String(incidentTrack) : ''
}
