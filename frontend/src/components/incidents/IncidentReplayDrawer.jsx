import { useCallback, useEffect, useState } from 'react'
import { getIncidentReplay } from '../../api/camerasApi'
import { normalizeError } from '../../api/client'
import SeverityBadge from '../common/SeverityBadge'
import LoadingState from '../common/LoadingState'
import ErrorState from '../common/ErrorState'
import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'

export default function IncidentReplayDrawer({ incident, open, onClose }) {
  const [replay, setReplay] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [frameIdx, setFrameIdx] = useState(0)

  const load = useCallback(async () => {
    if (!incident) return
    const id = incident.incident_id || incident.id
    if (!id) return
    setLoading(true)
    setReplay(null)
    setFrameIdx(0)
    try {
      const data = await getIncidentReplay(id)
      setReplay(data)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [incident])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  if (!open) return null

  const incidentTitle = incident?.incident_type || incident?.type || incident?.incident_id || 'Incident'
  const frames = replay?.frames || []
  const alerts = replay?.alerts || []
  const handoffs = replay?.handoffs || []
  // Phase 23: open-vocab results attached to replay
  const ovResults = replay?.open_vocab_results || []
  const currentFrame = frames[frameIdx]

  return (
    <aside className="detail-drawer" aria-label="Incident replay">
      {/* Header */}
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Forensic Replay</p>
          <h2>{incidentTitle}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close replay">
          x
        </button>
      </div>

      <div className="drawer-body">
        {loading && <LoadingState label="Loading replay manifest…" />}
        {error && <ErrorState message={error} onRetry={load} />}

        {replay && !loading && (
          <>
            {/* Incident summary */}
            <section style={{ marginBottom: 16 }}>
              <p style={{ margin: '0 0 5px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                Incident
              </p>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <SeverityBadge severity={incident?.severity} />
                <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                  {formatTimestamp(incident?.started_at || incident?.created_at)}
                </span>
                <span style={{ fontSize: '0.72rem', color: '#6b7280' }}>
                  {replay.frame_count} frames · {replay.alert_count} alerts
                </span>
              </div>
            </section>

            {/* Timeline scrubber */}
            {frames.length > 0 ? (
              <section style={{ marginBottom: 16 }}>
                <p style={{ margin: '0 0 5px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                  Frame Scrubber ({frameIdx + 1} / {frames.length})
                </p>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }}>
                  <button
                    className="ctrl-btn"
                    disabled={frameIdx <= 0}
                    onClick={() => setFrameIdx(i => Math.max(0, i - 1))}
                  >
                    ◀
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={frames.length - 1}
                    value={frameIdx}
                    onChange={e => setFrameIdx(Number(e.target.value))}
                    style={{ flex: 1 }}
                  />
                  <button
                    className="ctrl-btn"
                    disabled={frameIdx >= frames.length - 1}
                    onClick={() => setFrameIdx(i => Math.min(frames.length - 1, i + 1))}
                  >
                    ▶
                  </button>
                </div>

                {currentFrame && (
                  <div style={{ fontSize: '0.72rem', background: '#0a0f1a', borderRadius: 4, padding: '6px 10px', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    <span style={{ color: '#6b7280' }}>{formatTimestamp(currentFrame.timestamp)}</span>
                    <span style={{ color: '#9ca3af' }}>Frame #{currentFrame.frame_id ?? '—'}</span>
                    {(currentFrame.track_ids || []).length > 0 && (
                      <span style={{ color: '#1890ff' }}>{currentFrame.track_ids.length} tracks</span>
                    )}
                    {(currentFrame.event_ids || []).length > 0 && (
                      <span style={{ color: '#fa8c16' }}>{currentFrame.event_ids.length} events</span>
                    )}
                  </div>
                )}
              </section>
            ) : (
              <EmptyState message="No timeline frames recorded for this incident." />
            )}

            {/* Handoff chain */}
            {handoffs.length > 0 && (
              <section style={{ marginBottom: 16 }}>
                <p style={{ margin: '0 0 6px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                  Camera Handoff Chain ({handoffs.length})
                </p>
                <ol style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 180, overflowY: 'auto' }}>
                  {handoffs.map((ho, idx) => {
                    const stateColor = {
                      predicted: '#a78bfa', candidate: '#60a5fa',
                      confirmed: '#34d399', rejected: '#f87171', expired: '#6b7280',
                    }[ho.state] ?? '#9ca3af'
                    const ev = ho.evidence ?? {}
                    return (
                      <li
                        key={ho.handoff_id ?? idx}
                        style={{
                          borderLeft: `3px solid ${stateColor}`,
                          background: '#0a0f1a',
                          borderRadius: '0 4px 4px 0',
                          padding: '5px 8px',
                          marginBottom: 6,
                          fontSize: '0.72rem',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 3 }}>
                          <span style={{ color: stateColor, fontWeight: 600, fontSize: '0.65rem' }}>
                            {(ho.state ?? 'unknown').toUpperCase()}
                          </span>
                          <span style={{ color: '#e5e7eb', fontFamily: 'monospace' }}>
                            {ho.source_camera} → {ho.target_camera}
                          </span>
                          <span style={{ color: '#9ca3af' }}>
                            {Math.round((ho.confidence ?? 0) * 100)}% conf
                          </span>
                          {ho.eta_seconds != null && (
                            <span style={{ color: '#fbbf24' }}>ETA {ho.eta_seconds.toFixed(0)}s</span>
                          )}
                        </div>
                        {ho.route && ho.route.length > 0 && (
                          <div style={{ fontSize: '0.65rem', color: '#6b7280', marginBottom: 2, fontFamily: 'monospace' }}>
                            Route: {ho.route.join(' → ')}
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: '0.65rem', color: '#6b7280' }}>
                          {ev.topology_score != null && <span>Topo {Math.round(ev.topology_score * 100)}%</span>}
                          {ev.temporal_score != null && <span>Time {Math.round(ev.temporal_score * 100)}%</span>}
                          {ev.motion_score != null && <span>Motion {Math.round(ev.motion_score * 100)}%</span>}
                          {ev.identity_score != null && <span>ID {Math.round(ev.identity_score * 100)}%</span>}
                          {ev.appearance_score != null && <span>App {Math.round(ev.appearance_score * 100)}%</span>}
                        </div>
                        {ho.identity_id && (
                          <div style={{ fontSize: '0.62rem', color: '#9ca3af', marginTop: 2 }}>
                            Identity: {ho.identity_id.slice(0, 12)}
                          </div>
                        )}
                      </li>
                    )
                  })}
                </ol>
              </section>
            )}

            {/* Phase 23: open-vocab detections in replay */}
            {ovResults.length > 0 && (
              <section style={{ marginBottom: 16 }}>
                <p style={{ margin: '0 0 6px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                  Open-Vocab Detections ({ovResults.reduce((s, r) => s + (r.open_vocab_detections?.length || 0), 0)})
                </p>
                <ol style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 160, overflowY: 'auto' }}>
                  {ovResults.flatMap((r, ri) =>
                    (r.open_vocab_detections || []).map((det, di) => (
                      <li key={`${ri}-${di}`} style={{
                        background: '#0a0f1a', borderRadius: 4, padding: '4px 8px', marginBottom: 4,
                        borderLeft: '3px solid #a78bfa', fontSize: '0.7rem',
                      }}>
                        <strong style={{ color: '#c4b5fd' }}>{det.label || '—'}</strong>
                        {det.confidence != null && (
                          <span style={{ color: '#6b7280', marginLeft: 6 }}>
                            {(det.confidence * 100).toFixed(1)}%
                          </span>
                        )}
                        {det.severity && (
                          <span style={{ color: '#fbbf24', marginLeft: 6, fontWeight: 600 }}>{det.severity}</span>
                        )}
                        <span style={{ color: '#4b5563', marginLeft: 6, fontFamily: 'monospace', fontSize: '0.62rem' }}>
                          frame #{r.frame_id ?? '—'}
                        </span>
                      </li>
                    ))
                  )}
                </ol>
              </section>
            )}

            {/* Related alerts */}
            {alerts.length > 0 && (
              <section>
                <p style={{ margin: '0 0 6px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                  Related Alerts ({alerts.length})
                </p>
                <ol className="alert-list" style={{ maxHeight: 200, overflowY: 'auto' }}>
                  {alerts.map(alert => (
                    <li key={alert.alert_id || alert.id} style={{ fontSize: '0.72rem' }}>
                      <span style={{ color: '#9ca3af' }}>{formatTimestamp(alert.created_at)}</span>
                      <strong style={{ color: '#e6e6e6' }}>{alert.title || alert.alert_id}</strong>
                      <SeverityBadge severity={alert.severity} compact />
                      {/* Phase 20 — identity / watchlist signals in replay */}
                      {alert.metadata?.identity_id && (
                        <div style={{ marginTop: 2, display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: '0.65rem' }}>
                          <span style={{ color: '#8b949e', fontFamily: 'monospace' }}>
                            ID: {String(alert.metadata.identity_id).slice(0, 12)}…
                          </span>
                          {alert.metadata.display_name && (
                            <span style={{ color: '#3fb950' }}>{alert.metadata.display_name}</span>
                          )}
                          {alert.metadata.watchlist_severity && (
                            <span style={{
                              padding: '1px 5px',
                              borderRadius: '8px',
                              background: '#21262d',
                              color: {
                                critical: '#f85149', high: '#f0883e',
                                medium: '#e3b341', low: '#8b949e',
                              }[alert.metadata.watchlist_severity] || '#8b949e',
                              fontWeight: 600,
                              textTransform: 'uppercase',
                            }}>
                              {alert.metadata.watchlist_severity}
                            </span>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </>
        )}
      </div>
    </aside>
  )
}
