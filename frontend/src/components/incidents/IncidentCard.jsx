import IncidentSeverityBadge from './IncidentSeverityBadge'
import { compactList, formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

export default function IncidentCard({ incident, selected, onSelect }) {
  const incidentId = incident.incident_id || incident.id
  return (
    <article className={`incident-card ${selected ? 'selected' : ''}`} onClick={() => onSelect(incidentId)}>
      <div className="incident-card-top">
        <IncidentSeverityBadge severity={incident.severity} />
        <span className="state-chip">{incident.state || 'open'}</span>
      </div>
      <h3>{incident.summary || incident.incident_type || incidentId || 'Incident'}</h3>
      <div className="incident-grid">
        <span>ID</span><strong>{incidentId || 'N/A'}</strong>
        <span>Cameras</span><strong>{compactList(incident.camera_ids)}</strong>
        <span>Tracks</span><strong>{compactList(incident.track_ids)}</strong>
        <span>Risk</span><strong>{formatPercent(incident.risk_score)}</strong>
        <span>Timeline</span><strong>{incident.timeline_refs?.length ?? incident.timeline_count ?? 0}</strong>
        <span>Updated</span><strong>{formatTimestamp(incident.updated_at)}</strong>
      </div>
    </article>
  )
}
