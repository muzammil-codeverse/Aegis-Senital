import EmptyState from '../common/EmptyState'
import { formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

export default function IncidentTimeline({ incident }) {
  if (!incident) {
    return <EmptyState message="Select an incident to inspect its evidence timeline." />
  }
  const events = Array.isArray(incident.events) ? incident.events : []
  const anomalies = Array.isArray(incident.anomalies) ? incident.anomalies : []
  const timelineRefs = Array.isArray(incident.timeline_refs) ? incident.timeline_refs : []

  return (
    <section className="incident-timeline">
      <div className="panel-subheader">
        <h3>Incident Timeline</h3>
        <span>{events.length} events / {anomalies.length} anomalies / {timelineRefs.length} refs</span>
      </div>
      {events.length === 0 && anomalies.length === 0 && timelineRefs.length === 0 ? (
        <EmptyState message="No timeline evidence attached yet." />
      ) : (
        <ol className="timeline-list">
          {events.map((event, index) => (
            <li key={`event-${event.event_id || index}`}>
              <span>{formatTimestamp(event.timestamp || incident.updated_at)}</span>
              <strong>{event.event_type || 'event'}</strong>
              <em>risk {formatPercent(event.risk_score || event.severity_score)}</em>
            </li>
          ))}
          {anomalies.map((anomaly, index) => (
            <li key={`anomaly-${anomaly.anomaly_id || index}`}>
              <span>{formatTimestamp(anomaly.timestamp || incident.updated_at)}</span>
              <strong>{anomaly.anomaly_type || 'anomaly'}</strong>
              <em>score {formatPercent(anomaly.score || anomaly.risk_score)}</em>
            </li>
          ))}
          {timelineRefs.map((ref, index) => (
            <li key={`ref-${index}`}>
              <span>{formatTimestamp(ref.timestamp || incident.updated_at)}</span>
              <strong>timeline ref</strong>
              <em>{ref.path || ref.timeline_id || String(ref)}</em>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
