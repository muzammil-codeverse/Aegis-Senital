import SeverityBadge from '../common/SeverityBadge'
import AlertControls from './AlertControls'
import { compactList, formatPercent } from '../../utils/formatters'
import { formatAge, formatTimestamp } from '../../utils/time'

export default function AlertCard({
  alert,
  selected,
  onSelect,
  onAcknowledge,
  onResolve,
  onEscalate,
  busy,
}) {
  const updatedAt = alert.updated_at || alert.created_at
  return (
    <article className={`alert-card ${selected ? 'selected' : ''}`} onClick={() => onSelect(alert.alert_id)}>
      <div className="alert-card-header">
        <SeverityBadge severity={alert.severity} compact />
        <span className="state-chip">{alert.state || 'new'}</span>
        <span className="alert-age">{formatAge(alert.age_seconds ?? alert.created_at)}</span>
      </div>
      <h3>{alert.title || 'Untitled alert'}</h3>
      <p>{alert.description || 'No description supplied by runtime.'}</p>
      <div className="alert-metrics">
        <span>Risk <strong>{formatPercent(alert.risk_score)}</strong></span>
        <span>Conf <strong>{formatPercent(alert.confidence)}</strong></span>
        <span>Updated <strong>{formatTimestamp(updatedAt)}</strong></span>
      </div>
      <div className="alert-context">
        <span>Cameras: <strong>{compactList(alert.camera_ids)}</strong></span>
        <span>Tracks: <strong>{compactList(alert.track_ids)}</strong></span>
      </div>
      <AlertControls
        alert={alert}
        onAcknowledge={onAcknowledge}
        onResolve={onResolve}
        onEscalate={onEscalate}
        busy={busy}
      />
    </article>
  )
}
