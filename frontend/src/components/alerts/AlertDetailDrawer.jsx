import SeverityBadge from '../common/SeverityBadge'
import LoadingState from '../common/LoadingState'
import ErrorState from '../common/ErrorState'
import AlertControls from './AlertControls'
import { compactList, formatPercent } from '../../utils/formatters'
import { formatDateTime, formatTimestamp } from '../../utils/time'

export default function AlertDetailDrawer({
  alert,
  history = [],
  open,
  loading,
  error,
  onClose,
  onAcknowledge,
  onResolve,
  onEscalate,
  busy,
}) {
  if (!open) return null
  return (
    <aside className="detail-drawer" aria-label="Alert details">
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Alert Detail</p>
          <h2>{alert?.title || 'Loading alert'}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close alert detail">
          x
        </button>
      </div>
      {loading && <LoadingState label="Loading alert detail" />}
      {error && <ErrorState message={error} />}
      {alert && (
        <>
          <div className="drawer-summary">
            <SeverityBadge severity={alert.severity} />
            <span className="state-chip">{alert.state}</span>
            <span>Risk {formatPercent(alert.risk_score)}</span>
            <span>Confidence {formatPercent(alert.confidence)}</span>
          </div>
          <p className="drawer-description">{alert.description}</p>
          <div className="drawer-grid">
            <span>Alert ID</span><strong>{alert.alert_id}</strong>
            <span>Incident</span><strong>{alert.incident_id || 'N/A'}</strong>
            <span>Cameras</span><strong>{compactList(alert.camera_ids)}</strong>
            <span>Tracks</span><strong>{compactList(alert.track_ids)}</strong>
            <span>Identities</span><strong>{compactList(alert.identity_ids)}</strong>
            <span>Created</span><strong>{formatDateTime(alert.created_at)}</strong>
            <span>Updated</span><strong>{formatDateTime(alert.updated_at)}</strong>
          </div>
          <AlertControls
            alert={alert}
            onAcknowledge={onAcknowledge}
            onResolve={onResolve}
            onEscalate={onEscalate}
            busy={busy}
          />
          <section className="drawer-section">
            <h3>History</h3>
            {history.length === 0 ? (
              <p className="muted">No transition history recorded.</p>
            ) : (
              <ol className="history-list">
                {history.map((record, index) => (
                  <li key={`${record.timestamp}-${index}`}>
                    <span>{formatTimestamp(record.timestamp)}</span>
                    <strong>{record.record_type || 'record'}</strong>
                    <em>{record.to_state || record.action || record.channel || record.from_state || 'stored'}</em>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </aside>
  )
}
