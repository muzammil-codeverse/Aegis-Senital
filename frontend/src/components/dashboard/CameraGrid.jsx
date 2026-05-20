import EmptyState from '../common/EmptyState'
import LoadingState from '../common/LoadingState'
import SeverityBadge from '../common/SeverityBadge'
import { useStreamControls } from '../../hooks/useStreamControls'

const PRIORITY_COLOR = { critical: '#ff4d4f', high: '#fa8c16', normal: '#52c41a', low: '#8c8c8c' }
const STATUS_COLOR   = { online: '#52c41a', offline: '#8c8c8c', degraded: '#fa8c16', error: '#ff4d4f', disabled: '#595959', maintenance: '#722ed1' }
const STREAM_COLOR   = { running: '#52c41a', starting: '#1890ff', paused: '#fa8c16', stopped: '#8c8c8c', error: '#ff4d4f' }

const SIM_SOURCE_LABEL = {
  fixed_cctv: 'Fixed CCTV',
  ptz_camera: 'PTZ Camera',
  drone_camera: 'Drone Cam',
  simulation_virtual_camera: 'Virtual Cam',
  uploaded_video_source: 'Uploaded',
  scenario_observation_source: 'Scenario',
}

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

function SimBadge() {
  return (
    <span style={{
      fontSize: '0.55rem', padding: '1px 4px', borderRadius: 2,
      background: 'rgba(114,46,209,0.15)', color: '#9b59b6',
      border: '1px solid rgba(114,46,209,0.35)', textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>
      SIM
    </span>
  )
}

function FeedPlaceholder({ camera, frame }) {
  if (camera.snapshotUrl) {
    return (
      <img
        src={camera.snapshotUrl}
        alt={`${camera.camera_id} visual snapshot`}
        style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
      />
    )
  }
  if (camera.simulated) {
    const feedLabel = camera.status === 'offline'
      ? 'Camera Offline'
      : camera.status === 'maintenance'
        ? 'Under Maintenance'
        : camera.last_observation_at
          ? 'Last Observation Recorded'
          : 'Awaiting Visual Capture'
    return (
      <div style={{
        fontSize: '0.63rem', color: '#6b7280', textAlign: 'center',
        padding: '6px 2px', lineHeight: 1.4,
      }}>
        <div style={{ color: '#4b5563', marginBottom: 2 }}>Simulated City CCTV</div>
        <div style={{ color: camera.status === 'online' ? '#52c41a' : '#fa8c16' }}>{feedLabel}</div>
        {camera.feed_uri && (
          <div style={{ color: '#374151', marginTop: 2, fontSize: '0.58rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={camera.feed_uri}>
            {camera.feed_uri}
          </div>
        )}
      </div>
    )
  }
  return (
    <div style={{ fontSize: '0.68rem', color: '#6b7280', textAlign: 'center' }}>
      {frame?.detections?.length > 0
        ? <span style={{ color: '#fa8c16' }}>{frame.detections.length} det</span>
        : <span>no detections</span>}
      {frame?.tracks?.length > 0 && (
        <span style={{ color: '#1890ff', marginLeft: 6 }}>{frame.tracks.length} trk</span>
      )}
    </div>
  )
}

function CameraCard({ camera, frame, streamState, alertCount, selected, onSelect, streamControls }) {
  const isBusy = streamControls.busyCameraId === camera.camera_id
  const riskSeverity = camera.riskSeverity || 'info'
  const sState = streamState || (camera.simulated ? 'simulation' : 'stopped')
  const isSimulated = Boolean(camera.simulated)

  return (
    <article
      className={`camera-card${selected ? ' camera-card--selected' : ''}${isSimulated ? ' camera-card--simulated' : ''}`}
      style={{
        cursor: 'pointer', position: 'relative',
        border: selected ? '1.5px solid #1890ff' : isSimulated ? '1px solid rgba(114,46,209,0.25)' : '1px solid transparent',
        borderRadius: 6,
      }}
      onClick={() => onSelect && onSelect(camera)}
    >
      {/* Header */}
      <div className="camera-card-top" style={{ gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
          <Dot color={STATUS_COLOR[camera.status] || '#8c8c8c'} />
          <strong style={{ fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{camera.name}</strong>
          {isSimulated && <SimBadge />}
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

      {/* Camera ID row for simulation cameras */}
      {isSimulated && (
        <div style={{ fontSize: '0.6rem', color: '#4b5563', padding: '1px 0 2px', display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ color: '#6b7280' }}>{camera.camera_id}</span>
          {camera.source_type && (
            <span style={{ color: '#9b59b6', fontSize: '0.58rem' }}>{SIM_SOURCE_LABEL[camera.source_type] || camera.source_type}</span>
          )}
          {camera.district && (
            <span style={{ color: '#4b5563', fontSize: '0.58rem' }}>{camera.district}</span>
          )}
        </div>
      )}

      {/* Feed / snapshot preview area */}
      <div className="camera-feed-placeholder" style={{ position: 'relative', minHeight: 64 }}>
        <FeedPlaceholder camera={camera} frame={frame} />
        {(camera.status === 'offline' || camera.status === 'error') && !isSimulated && (
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
        {isSimulated ? (
          <>
            <span>Zone <strong>{camera.zone_name || camera.zone || '—'}</strong></span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Dot color={STATUS_COLOR[camera.status] || '#8c8c8c'} />
              <span style={{ color: STATUS_COLOR[camera.status] || '#6b7280' }}>{camera.status}</span>
            </span>
            <span><PriorityTag priority={camera.priority} /></span>
            {camera.supported_detections?.length > 0 && (
              <span style={{ color: '#6b7280', fontSize: '0.58rem' }} title={camera.supported_detections.join(', ')}>
                {camera.supported_detections.slice(0, 2).join(', ')}{camera.supported_detections.length > 2 ? ` +${camera.supported_detections.length - 2}` : ''}
              </span>
            )}
            {camera.last_observation_at && (
              <span style={{ color: '#4b5563', fontSize: '0.6rem' }}>
                obs {new Date(camera.last_observation_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </>
        ) : (
          <>
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
          </>
        )}
      </div>

      {/* Controls — only for non-simulated cameras */}
      {!isSimulated && (
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
      )}

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
  title,
  eyebrow,
}) {
  const streamControls = useStreamControls({ onSuccess: onRefresh })
  const simCount = cameras.filter(c => c.simulated).length
  const liveCount = cameras.length - simCount

  const gridTitle = title || (simCount > 0 && liveCount === 0 ? 'Simulated City Network' : 'Camera Grid')
  const gridEyebrow = eyebrow || (simCount > 0 && liveCount === 0 ? 'Simulated City CCTV' : 'Camera Operations')

  if (loading) return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div><p className="eyebrow">{gridEyebrow}</p><h2>{gridTitle}</h2></div>
      </div>
      <LoadingState message="Loading cameras…" />
    </section>
  )

  return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">{gridEyebrow}</p>
          <h2>{gridTitle}</h2>
          {simCount > 0 && (
            <p style={{ fontSize: '0.65rem', color: '#6b7280', margin: '2px 0 0' }}>
              {simCount} camera source{simCount !== 1 ? 's' : ''} registered
              {liveCount > 0 ? ` · ${liveCount} live` : ''}
            </p>
          )}
        </div>
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
        <EmptyState message={simCount > 0 ? "No active observations." : "No simulation cameras loaded. Refresh sources or run visual setup."} />
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
