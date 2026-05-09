import SeverityBadge from '../common/SeverityBadge'

const STATUS_BANNER = {
  offline: { label: 'OFFLINE', color: '#ff7875', bg: 'rgba(0,0,0,0.6)' },
  degraded: { label: 'DEGRADED', color: '#fa8c16', bg: 'rgba(0,0,0,0.5)' },
  error: { label: 'ERROR', color: '#ff4d4f', bg: 'rgba(60,0,0,0.6)' },
  disabled: { label: 'DISABLED', color: '#8c8c8c', bg: 'rgba(0,0,0,0.6)' },
}

function OverlayDetectionBox({ bbox, label }) {
  if (!Array.isArray(bbox) || bbox.length < 4) return null
  const [x1, y1, x2, y2] = bbox
  return (
    <div
      style={{
        position: 'absolute',
        left: `${x1 / 6.4}%`,
        top: `${y1 / 6.4}%`,
        width: `${(x2 - x1) / 6.4}%`,
        height: `${(y2 - y1) / 6.4}%`,
        border: '1.5px solid #52c41a',
        boxSizing: 'border-box',
        pointerEvents: 'none',
      }}
    >
      {label && (
        <span style={{
          position: 'absolute',
          top: -16,
          left: 0,
          fontSize: '0.6rem',
          background: 'rgba(0,0,0,0.7)',
          color: '#52c41a',
          padding: '0 3px',
          whiteSpace: 'nowrap',
        }}>
          {label}
        </span>
      )}
    </div>
  )
}

export default function LiveVideoSurface({ camera, latestFrame, selected, onSelect }) {
  if (!camera) return null

  const banner = STATUS_BANNER[camera.status]
  const hasFrame = latestFrame && latestFrame.status === 'ok'
  const detections = hasFrame ? (latestFrame.detections || []) : []
  const overlays = hasFrame ? (latestFrame.overlays || []) : []

  return (
    <div
      className={`live-video-surface${selected ? ' live-video-surface--selected' : ''}`}
      onClick={() => onSelect && onSelect(camera)}
      style={{
        position: 'relative',
        background: '#0a0f1a',
        border: selected ? '1.5px solid #1890ff' : '1px solid #1f2937',
        borderRadius: 6,
        overflow: 'hidden',
        cursor: 'pointer',
        minHeight: 160,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Camera header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(0,0,0,0.4)', zIndex: 2 }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#e6e6e6' }}>{camera.name}</span>
        <SeverityBadge severity={camera.riskSeverity || 'info'} compact />
      </div>

      {/* Video / snapshot region */}
      <div style={{ flex: 1, position: 'relative', minHeight: 120, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {/* Overlay layer — detection boxes */}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 3 }}>
          {detections.map((det, i) => (
            <OverlayDetectionBox
              key={i}
              bbox={det.bbox}
              label={det.type ? `${det.type} ${det.confidence ? Math.round(det.confidence * 100) + '%' : ''}` : null}
            />
          ))}
          {overlays.map((ov, i) => (
            <OverlayDetectionBox key={`ov-${i}`} bbox={ov.bbox} label={ov.label} />
          ))}
        </div>

        {/* Placeholder content */}
        <div style={{ textAlign: 'center', color: '#4a5568', fontSize: '0.72rem', zIndex: 1, padding: 12 }}>
          {hasFrame ? (
            <>
              <div style={{ color: '#6b7280' }}>Frame #{latestFrame.frame_id}</div>
              {detections.length > 0 && (
                <div style={{ color: '#fa8c16', marginTop: 2 }}>{detections.length} detection{detections.length !== 1 ? 's' : ''}</div>
              )}
              <div style={{ color: '#374151', marginTop: 2, fontSize: '0.65rem' }}>
                {new Date(latestFrame.timestamp * 1000).toLocaleTimeString()}
              </div>
            </>
          ) : (
            <>
              <div>RTSP · WebRTC · HLS</div>
              <div style={{ marginTop: 4, fontSize: '0.65rem', color: '#374151' }}>Live stream slot</div>
            </>
          )}
        </div>

        {/* Status banner overlay */}
        {banner && (
          <div style={{
            position: 'absolute',
            inset: 0,
            background: banner.bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 4,
          }}>
            <span style={{ color: banner.color, fontWeight: 700, fontSize: '0.85rem', letterSpacing: 2 }}>
              {banner.label}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 10px', background: 'rgba(0,0,0,0.35)', fontSize: '0.65rem', color: '#6b7280', zIndex: 2 }}>
        <span>{camera.zone || 'no zone'}</span>
        <span>{camera.source_type}</span>
        <span style={{ textTransform: 'uppercase', color: camera.status === 'online' ? '#52c41a' : '#6b7280' }}>{camera.status}</span>
      </div>
    </div>
  )
}
