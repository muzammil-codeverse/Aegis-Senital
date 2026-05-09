import { useCallback, useEffect, useState } from 'react'
import { getCameraTimeline } from '../../api/camerasApi'
import { normalizeError } from '../../api/client'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatTimestamp } from '../../utils/time'

const POLL_MS = 15000

export default function CameraTimelinePanel({ cameraId, onSelectFrame }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedIdx, setSelectedIdx] = useState(null)

  const load = useCallback(async () => {
    if (!cameraId) return
    setLoading(true)
    try {
      const result = await getCameraTimeline(cameraId, { limit: 50 })
      setItems([...result.items].reverse())
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [cameraId])

  useEffect(() => {
    setItems([])
    setSelectedIdx(null)
    load()
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [load])

  function handleSelect(item, idx) {
    setSelectedIdx(idx)
    onSelectFrame && onSelectFrame(item)
  }

  return (
    <section className="panel camera-timeline-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Forensic Timeline</p>
          <h2>Camera Events</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="count-pill">{items.length}</span>
          <button className="ctrl-btn" onClick={load} style={{ fontSize: '0.7rem' }} title="Refresh">↺</button>
        </div>
      </div>

      {loading && items.length === 0 && <LoadingState label="Loading timeline" />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState message={cameraId ? 'No timeline entries for this camera.' : 'Select a camera to view timeline.'} />
      )}

      {items.length > 0 && (
        <ol className="timeline-list" style={{ maxHeight: 280, overflowY: 'auto' }}>
          {items.map((item, idx) => {
            const trackCount = (item.track_ids || []).length
            const eventCount = (item.event_ids || []).length
            const incCount = (item.incident_ids || []).length
            const isSelected = selectedIdx === idx
            return (
              <li
                key={item.frame_id != null ? `f-${item.frame_id}` : `t-${idx}`}
                onClick={() => handleSelect(item, idx)}
                style={{
                  cursor: 'pointer',
                  background: isSelected ? '#0d2137' : undefined,
                  borderLeft: isSelected ? '2px solid #1890ff' : '2px solid transparent',
                  paddingLeft: 6,
                }}
              >
                <span style={{ color: '#6b7280' }}>{formatTimestamp(item.timestamp)}</span>
                <strong style={{ color: '#e6e6e6' }}>#{item.frame_id ?? '—'}</strong>
                <span style={{ display: 'flex', gap: 5, fontSize: '0.65rem', flexWrap: 'wrap' }}>
                  {trackCount > 0 && <span style={{ color: '#1890ff' }}>{trackCount} trk</span>}
                  {eventCount > 0 && <span style={{ color: '#fa8c16' }}>{eventCount} evt</span>}
                  {incCount > 0 && <span style={{ color: '#ff4d4f' }}>{incCount} inc</span>}
                  {(item.handoff_events || []).length > 0 && (
                    <span
                      style={{
                        color: '#a78bfa',
                        background: '#a78bfa18',
                        border: '1px solid #a78bfa44',
                        borderRadius: 3,
                        padding: '0 4px',
                        fontSize: '0.62rem',
                      }}
                      title={`Handoffs: ${(item.handoff_events || []).join(', ')}`}
                    >
                      {(item.handoff_events || []).length} HO
                    </span>
                  )}
                  {/* Phase 23: open-vocab scan references in timeline */}
                  {(item.open_vocab_scan_ids || []).length > 0 && (
                    <span
                      style={{
                        color: '#c4b5fd',
                        background: '#c4b5fd18',
                        border: '1px solid #c4b5fd44',
                        borderRadius: 3,
                        padding: '0 4px',
                        fontSize: '0.62rem',
                      }}
                      title={`Open-Vocab scans: ${(item.open_vocab_scan_ids || []).join(', ')}`}
                    >
                      OV
                    </span>
                  )}
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
