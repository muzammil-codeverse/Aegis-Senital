import EmptyState from '../common/EmptyState'
import LoadingState from '../common/LoadingState'
import SeverityBadge from '../common/SeverityBadge'
import { useStreamControls } from '../../hooks/useStreamControls'

const PRIORITY_COLOR = { critical: '#ff4d4f', high: '#fa8c16', normal: '#52c41a', low: '#8c8c8c' }
const STATUS_COLOR   = { online: '#52c41a', offline: '#8c8c8c', degraded: '#fa8c16', error: '#ff4d4f', disabled: '#595959' }
const STREAM_COLOR   = { running: '#52c41a', starting: '#1890ff', paused: '#fa8c16', stopped: '#8c8c8c', error: '#ff4d4f' }

function Dot({ color }) {
  return <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0 }} />
}

function PriorityTag({ priority }) {
  const color = PRIORITY_COLOR[priority] || '#8c8c8c'
  return (
    <span style={{ fontSize: '0.6rem', padding: '0 4px', borderRadius: 2, border: `1px solid ${color}`, color, textTransform: 'uppercase' }}>
      {priority}
    </span>
  )
}

function FrameAge({ frame }) {
  if (!frame || frame.status !== 'ok') return <span style={{ color: '#4b5563', fontSize: '0.65rem' }}>no frame</span>
  if (frame.stale) return <span style={{ color: '#fa8c16', fontSize: '0.65rem' }}>stale {frame.age_seconds != null ? `${frame.age_seconds}s` : ''}</span>
  return <span style={{ color: '#52c41a', fontSize: '0.65rem' }}>{frame.age_seconds != null ? `${frame.age_seconds}s ago` : 'live'}</span>
}

function StreamStateDot({ streamState }) {
  const color = STREAM_COLOR[streamState] || '#4b5563'
  return <Dot color={color} />
}

function CameraCard({ camera, frame, streamState, alertCount, selected, onSelect, streamControls }) {
  const isBusy = streamControls.busyCameraId === camera.camera_id
  const riskSeverity = camera.riskSeverity || 'info'
  const sState = streamState || 'stopped'

  return (
    <article
      className={`camera-card${selected ? ' camera-card--selected' : ''}`}
      style={{
        cursor: 'pointer', position: 'relative',
        border: selected ? '1.5px solid #1890ff' : '1px solid transparent',
        borderRadius: 6,
      }}
      onClick={() => onSelect && onSelect(camera)}
    >
      {/* Header */}
      <div className="camera-card-top" style={{ gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
          <Dot color={STATUS_COLOR[camera.status] || '#8c8c8c'} />
          <strong style={{ fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{camera.name}</strong>
        </div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexShrink: 0 }}>
          {alertCount > 0 && (
            <span style={{ fontSize: '0.6rem', background: '#ff4d4f20', color: '#ff4d4f', border: '1px solid #ff4d4f', borderRadius: 3, padding: '0 4px' }}>
              {alertCount}
            </span>
          )}
          <SeverityBadge severity={riskSeverity} compact />
        </div>
      </div>

      {/* Feed / snapshot preview area */}
      <div className="camera-feed-placeholder" style={{ position: 'relative', minHeight: 64 }}>
        <div style={{ fontSize: '0.68rem', color: '#6b7280', textAlign: 'center' }}>
          {frame?.detections?.length > 0
            ? <span style={{ color: '#fa8c16' }}>{frame.detections.length} det</span>
            : <span>no detections</span>}
          {frame?.tracks?.length > 0 && (
            <span style={{ color: '#1890ff', marginLeft: 6 }}>{frame.tracks.length} trk</span>
          )}
        </div>
        {(camera.status === 'offline' || camera.status === 'error') && (
          <div style={{
            position: 'absolute', inset: 0,
            background: camera.status === 'error' ? 'rgba(80,0,0,0.5)' : 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.68rem', color: STATUS_COLOR[camera.status],
          }}>
            {camera.status.toUpperCase()}
          </div>
        )}
      </div>

      {/* Meta */}
      <div className="camera-card-meta" style={{ fontSize: '0.67rem', rowGap: 2 }}>
        <span>Zone <strong>{camera.zone || '—'}</strong></span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <StreamStateDot streamState={sState} />
          <span style={{ color: STREAM_COLOR[sState] || '#6b7280' }}>{sState}</span>
        </span>
        <span><PriorityTag priority={camera.priority} /></span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <FrameAge frame={frame} />
        </span>
        {camera.last_event_at && (
          <span style={{ color: '#4b5563' }}>evt {new Date(camera.last_event_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
        )}
      </div>

      {/* Controls */}
      <div
        className="camera-card-controls"
        style={{ display: 'flex', gap: 3, marginTop: 5, flexWrap: 'wrap' }}
        onClick={e => e.stopPropagation()}
      >
        <button className="ctrl-btn ctrl-btn-start"   disabled={isBusy} onClick={() => streamControls.start(camera.camera_id)}>▶</button>
        <button className="ctrl-btn ctrl-btn-stop"    disabled={isBusy} onClick={() => streamControls.stop(camera.camera_id)}>■</button>
        <button className="ctrl-btn ctrl-btn-pause"   disabled={isBusy} onClick={() => streamControls.pause(camera.camera_id)}>⏸</button>
        <button className="ctrl-btn ctrl-btn-restart" disabled={isBusy} onClick={() => streamControls.restart(camera.camera_id)}>↺</button>
      </div>

      {isBusy && (
        <div style={{ position: 'absolute', top: 4, right: 4, fontSize: '0.6rem', color: '#1890ff' }}>···</div>
      )}
    </article>
  )
}

export default function CameraGrid({
  cameras = [],
  framesByCameraId = {},
  streamStatesByCameraId = {},
  alertCountByCameraId = {},
  selectedCameraId,
  onCameraSelect,
  loading,
  error,
  onRefresh,
}) {
  const streamControls = useStreamControls({ onSuccess: onRefresh })

  if (loading) return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div><p className="eyebrow">Camera Operations</p><h2>Camera Grid</h2></div>
      </div>
      <LoadingState message="Loading cameras…" />
    </section>
  )

  return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div><p className="eyebrow">Camera Operations</p><h2>Camera Grid</h2></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="count-pill">{cameras.length}</span>
          {onRefresh && (
            <button className="ctrl-btn" onClick={onRefresh} style={{ fontSize: '0.7rem' }} title="Refresh">↺</button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ padding: '6px 12px', fontSize: '0.72rem', color: '#ff7875', background: 'rgba(255,77,79,0.08)', borderRadius: 4, marginBottom: 6 }}>
          {error}
        </div>
      )}

      {cameras.length === 0 ? (
        <EmptyState message="No cameras registered. Add cameras via the API or cameras.yaml config." />
      ) : (
        <div className="camera-grid">
          {cameras.map(camera => (
            <CameraCard
              key={camera.camera_id}
              camera={camera}
              frame={framesByCameraId[camera.camera_id]}
              streamState={streamStatesByCameraId[camera.camera_id]?.state}
              alertCount={alertCountByCameraId[camera.camera_id] || 0}
              selected={camera.camera_id === selectedCameraId}
              onSelect={onCameraSelect}
              streamControls={streamControls}
            />
          ))}
        </div>
      )}

      {streamControls.error && (
        <div style={{ padding: '4px 12px', fontSize: '0.7rem', color: '#ff7875', marginTop: 4 }}>
          {streamControls.error}
        </div>
      )}
    </section>
  )
}
