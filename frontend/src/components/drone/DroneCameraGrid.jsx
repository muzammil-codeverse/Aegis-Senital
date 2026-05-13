import { useEffect } from 'react'

function FrameTile({ cameraName, frame, selected, onSelect, onRefresh }) {
  const badge = frame?.frame_available ? 'connected' : (frame?.status || 'disconnected')
  return (
    <article className={`case-subcard ${selected ? 'selected' : ''}`} style={{ padding: 8 }}>
      <div className="alert-card-header">
        <strong>{cameraName.replace('_', ' ')}</strong>
        <span className="state-chip">{badge}</span>
      </div>
      <div style={{ background: '#07111f', borderRadius: 6, minHeight: 120, marginTop: 8, overflow: 'hidden' }}>
        {frame?.frame_available && frame?.image_base64 ? (
          <img
            src={`data:${frame.content_type || 'image/jpeg'};base64,${frame.image_base64}`}
            alt={`Drone ${cameraName}`}
            style={{ width: '100%', height: 140, objectFit: 'cover', display: 'block' }}
          />
        ) : (
          <div style={{ color: '#94a3b8', fontSize: 12, padding: 12 }}>
            Disconnected or degraded simulated drone feed. Operator review required.
          </div>
        )}
      </div>
      <div className="button-row" style={{ marginTop: 8 }}>
        <button type="button" className="text-button" onClick={() => onSelect?.(cameraName)}>
          Select
        </button>
        <button type="button" className="text-button" onClick={() => onRefresh?.(cameraName)}>
          Refresh
        </button>
      </div>
    </article>
  )
}

export default function DroneCameraGrid({
  cameras = [],
  cameraFrames = {},
  selectedCamera,
  onSelectCamera,
  onRefreshCamera,
  autoRefresh = false,
}) {
  useEffect(() => {
    if (!autoRefresh || !onRefreshCamera) return undefined
    const timer = window.setInterval(() => {
      cameras.forEach(item => onRefreshCamera(item.camera_name))
    }, 4000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, cameras, onRefreshCamera])

  if (!cameras.length) {
    return <p className="muted">No simulated drone camera sources are available.</p>
  }

  return (
    <div className="drawer-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
      {cameras.map(item => (
        <FrameTile
          key={item.source_id || item.camera_name}
          cameraName={item.camera_name}
          frame={cameraFrames[item.camera_name]}
          selected={selectedCamera === item.camera_name}
          onSelect={onSelectCamera}
          onRefresh={onRefreshCamera}
        />
      ))}
    </div>
  )
}
