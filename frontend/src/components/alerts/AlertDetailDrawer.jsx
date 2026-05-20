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
  relatedCase,
  onViewCase,
  onCreateCaseFromEvent,
  caseBusy,
}) {
  if (!open) return null
  const uploadedVideo = alert?.metadata?.uploaded_video
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
          {(relatedCase || alert?.event_ids?.[0]) && (
            <div className="button-row">
              {relatedCase ? (
                <button type="button" className="text-button" disabled={caseBusy} onClick={onViewCase}>
                  View Case
                </button>
              ) : (
                <button type="button" className="text-button" disabled={caseBusy} onClick={onCreateCaseFromEvent}>
                  Create Case From Event
                </button>
              )}
            </div>
          )}
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
          {uploadedVideo ? (
            <section className="drawer-section">
              <h3>Uploaded Video Source</h3>
              <div className="drawer-grid">
                <span>Session</span><strong>{uploadedVideo.session_id || 'N/A'}</strong>
                <span>Video</span><strong>{uploadedVideo.original_filename || 'N/A'}</strong>
                <span>Frame</span><strong>{uploadedVideo.frame_index ?? 'N/A'}</strong>
                <span>Offset</span><strong>{uploadedVideo.time_offset_seconds != null ? `${Number(uploadedVideo.time_offset_seconds).toFixed(2)}s` : 'N/A'}</strong>
              </div>
              <div className="button-row">
                <button type="button" className="text-button" onClick={() => { window.location.hash = 'uploaded-video-analysis' }}>
                  Open Uploaded-Video Report
                </button>
              </div>
            </section>
          ) : null}
          {/* Phase 7 — scenario tracking context */}
          {alert.metadata?.has_tracking_view && alert.metadata?.run_id && (
            <section className="drawer-section">
              <h3>Scenario Tracking Context</h3>
              <div className="drawer-grid">
                <span>Scenario</span><strong style={{ fontFamily: 'monospace' }}>{alert.metadata.scenario_id || 'N/A'}</strong>
                <span>Run ID</span><strong style={{ fontFamily: 'monospace', fontSize: '0.7rem' }}>{alert.metadata.run_id}</strong>
                <span>Actor</span><strong>{alert.metadata.actor_id || 'N/A'}</strong>
                <span>Camera</span><strong>{alert.metadata.camera_id || 'N/A'}</strong>
                <span>Zone</span><strong>{alert.metadata.zone || 'N/A'}</strong>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="text-button"
                  style={{ color: '#1890ff' }}
                  onClick={() => { window.location.hash = `scenario-tracking/${alert.metadata.run_id}` }}
                >
                  View Tracking
                </button>
              </div>
            </section>
          )}
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
