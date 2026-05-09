import EmptyState from '../common/EmptyState'
import LoadingState from '../common/LoadingState'
import SeverityBadge from '../common/SeverityBadge'
import { useCameras } from '../../hooks/useCameras'
import { useStreamControls } from '../../hooks/useStreamControls'
import { useLatestFrames } from '../../hooks/useLatestFrames'
import { formatPercent } from '../../utils/formatters'

const PRIORITY_COLOR = { critical: '#ff4d4f', high: '#fa8c16', normal: '#52c41a', low: '#8c8c8c' }
const STATUS_COLOR = { online: '#52c41a', offline: '#8c8c8c', degraded: '#fa8c16', error: '#ff4d4f', disabled: '#595959' }

function StatusDot({ status }) {
  const color = STATUS_COLOR[status] || '#8c8c8c'
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, marginRight: 4 }} />
}

function PriorityTag({ priority }) {
  const color = PRIORITY_COLOR[priority] || '#8c8c8c'
  return (
    <span style={{ fontSize: '0.65rem', padding: '1px 5px', borderRadius: 3, border: `1px solid ${color}`, color, textTransform: 'uppercase' }}>
      {priority}
    </span>
  )
}

function CameraCard({ camera, frame, onSelect, streamControls }) {
  const isBusy = streamControls.busyCameraId === camera.camera_id
  const riskSeverity = camera.riskSeverity || 'info'

  return (
    <article
      className="camera-card"
      style={{ cursor: 'pointer', position: 'relative' }}
      onClick={() => onSelect && onSelect(camera)}
    >
      <div className="camera-card-top">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StatusDot status={camera.status} />
          <strong style={{ fontSize: '0.8rem' }}>{camera.name}</strong>
        </div>
        <SeverityBadge severity={riskSeverity} compact />
      </div>

      <div className="camera-feed-placeholder" style={{ position: 'relative', minHeight: 80 }}>
        {frame && frame.status === 'ok' ? (
          <div style={{ fontSize: '0.7rem', color: '#aaa', textAlign: 'center' }}>
            <div>Frame #{frame.frame_id}</div>
            {frame.detections?.length > 0 && (
              <div style={{ color: '#fa8c16' }}>{frame.detections.length} detection{frame.detections.length !== 1 ? 's' : ''}</div>
            )}
          </div>
        ) : (
          <>
            <span>Feed pending</span>
            <em>RTSP/WebRTC/HLS slot</em>
          </>
        )}
        {camera.status === 'offline' && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', color: '#ff7875' }}>
            OFFLINE
          </div>
        )}
        {camera.status === 'error' && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(80,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', color: '#ff4d4f' }}>
            ERROR
          </div>
        )}
      </div>

      <div className="camera-card-meta" style={{ fontSize: '0.7rem' }}>
        <span>ID <strong>{camera.camera_id}</strong></span>
        <span>Zone <strong>{camera.zone || '—'}</strong></span>
        <span>Src <strong>{camera.source_type}</strong></span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          Priority <PriorityTag priority={camera.priority} />
        </span>
        {camera.last_frame_at && (
          <span>Frame <strong>{new Date(camera.last_frame_at * 1000).toLocaleTimeString()}</strong></span>
        )}
        {camera.last_event_at && (
          <span>Event <strong>{new Date(camera.last_event_at * 1000).toLocaleTimeString()}</strong></span>
        )}
      </div>

      <div className="camera-card-controls" style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }} onClick={e => e.stopPropagation()}>
        <button
          className="ctrl-btn ctrl-btn-start"
          disabled={isBusy}
          onClick={() => streamControls.start(camera.camera_id)}
          title="Start stream"
        >Start</button>
        <button
          className="ctrl-btn ctrl-btn-stop"
          disabled={isBusy}
          onClick={() => streamControls.stop(camera.camera_id)}
          title="Stop stream"
        >Stop</button>
        <button
          className="ctrl-btn ctrl-btn-pause"
          disabled={isBusy}
          onClick={() => streamControls.pause(camera.camera_id)}
          title="Pause stream"
        >Pause</button>
        <button
          className="ctrl-btn ctrl-btn-restart"
          disabled={isBusy}
          onClick={() => streamControls.restart(camera.camera_id)}
          title="Restart stream"
        >Restart</button>
      </div>

      {isBusy && (
        <div style={{ position: 'absolute', top: 4, right: 4, fontSize: '0.65rem', color: '#1890ff' }}>
          ···
        </div>
      )}
    </article>
  )
}

export default function CameraGrid({ onCameraSelect } = {}) {
  const { cameras, loading, error, refresh } = useCameras()
  const { framesByCameraId } = useLatestFrames()
  const streamControls = useStreamControls({ onSuccess: refresh })

  if (loading) return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Camera Operations</p>
          <h2>Camera Grid</h2>
        </div>
      </div>
      <LoadingState message="Loading cameras…" />
    </section>
  )

  return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Camera Operations</p>
          <h2>Camera Grid</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="count-pill">{cameras.length}</span>
          <button className="ctrl-btn" onClick={refresh} title="Refresh cameras" style={{ fontSize: '0.7rem' }}>↺</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '8px 12px', fontSize: '0.75rem', color: '#ff7875', background: 'rgba(255,77,79,0.08)', borderRadius: 4, marginBottom: 8 }}>
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
              onSelect={onCameraSelect}
              streamControls={streamControls}
            />
          ))}
        </div>
      )}

      {streamControls.error && (
        <div style={{ padding: '6px 12px', fontSize: '0.72rem', color: '#ff7875', marginTop: 6 }}>
          Stream control error: {streamControls.error}
        </div>
      )}
    </section>
  )
}
