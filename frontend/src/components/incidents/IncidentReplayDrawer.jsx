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
