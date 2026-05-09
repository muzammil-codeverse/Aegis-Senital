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
      {/* Phase 20 — identity / watchlist signals */}
      {alert.metadata?.identity_id && (
        <div style={{ marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: '0.72rem' }}>
          <span style={{ color: '#8b949e' }}>
            ID: <strong style={{ color: '#e6edf3', fontFamily: 'monospace' }}>
              {String(alert.metadata.identity_id).slice(0, 12)}…
            </strong>
          </span>
          {alert.metadata.display_name && (
            <span style={{ color: '#3fb950' }}>{alert.metadata.display_name}</span>
          )}
          {alert.metadata.watchlist_severity && (
            <span style={{
              padding: '1px 6px',
              borderRadius: '10px',
              background: {
                critical: '#3d0000', high: '#3d1e00', medium: '#2d2100', low: '#1a1f2e',
              }[alert.metadata.watchlist_severity] || '#21262d',
              color: {
                critical: '#f85149', high: '#f0883e', medium: '#e3b341', low: '#8b949e',
              }[alert.metadata.watchlist_severity] || '#8b949e',
              fontWeight: 600,
              textTransform: 'uppercase',
              fontSize: '0.65rem',
            }}>
              {alert.metadata.watchlist_severity}
            </span>
          )}
          {alert.metadata.match_confidence != null && (
            <span style={{ color: '#8b949e' }}>
              match: <strong>{formatPercent(alert.metadata.match_confidence)}</strong>
            </span>
          )}
        </div>
      )}
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
