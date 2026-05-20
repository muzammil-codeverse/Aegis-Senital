const SEVERITY_COLOR = {
  weapon_detected: '#ff4d4f',
  suspect_movement: '#fa8c16',
  default: '#52c41a',
}

function handoffColor(reason) {
  for (const [key, col] of Object.entries(SEVERITY_COLOR)) {
    if ((reason || '').includes(key)) return col
  }
  return SEVERITY_COLOR.default
}

export default function CameraHandoffTimeline({ handoffs = [] }) {
  if (handoffs.length === 0) {
    return (
      <div style={{ color: '#4b5563', fontSize: '0.7rem', textAlign: 'center', padding: '10px 0' }}>
        No camera handoffs recorded — advance the scenario.
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      {/* Horizontal chain */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, paddingBottom: 4, minWidth: 'max-content' }}>
        {handoffs.map((h, i) => {
          const col = handoffColor(h.reason)
          const isLast = i === handoffs.length - 1
          return (
            <div key={h.handoff_id || i} style={{ display: 'flex', alignItems: 'center' }}>
              {/* Camera node */}
              <div
                title={`T+${h.offset_seconds}s — ${h.from_camera_id} → ${h.to_camera_id}\n${h.reason || ''}`}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center',
                  gap: 2, minWidth: 64,
                }}
              >
                <div style={{
                  width: 10, height: 10, borderRadius: '50%',
                  background: col, border: '1.5px solid #0d1117',
                  flexShrink: 0,
                }} />
                <div style={{ fontSize: '0.58rem', color: col, textAlign: 'center', lineHeight: 1.2 }}>
                  {h.from_camera_id?.replace('CAM-', '') || '?'}
                </div>
                <div style={{ fontSize: '0.52rem', color: '#4b5563' }}>T+{h.offset_seconds}s</div>
              </div>
              {/* Arrow to next */}
              {!isLast && (
                <div style={{
                  height: 1.5, width: 20, background: col,
                  opacity: 0.5, flexShrink: 0, marginTop: -14,
                }} />
              )}
              {/* Last node adds the to_camera_id */}
              {isLast && (
                <>
                  <div style={{
                    height: 1.5, width: 20, background: col,
                    opacity: 0.5, flexShrink: 0, marginTop: -14,
                  }} />
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, minWidth: 64 }}>
                    <div style={{
                      width: 10, height: 10, borderRadius: '50%',
                      background: '#6b7280', border: '1.5px solid #0d1117', flexShrink: 0,
                    }} />
                    <div style={{ fontSize: '0.58rem', color: '#9ca3af', textAlign: 'center', lineHeight: 1.2 }}>
                      {h.to_camera_id?.replace('CAM-', '') || '?'}
                    </div>
                    <div style={{ fontSize: '0.52rem', color: '#4b5563' }}>→</div>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* Detail rows */}
      <div style={{ marginTop: 6 }}>
        {handoffs.map((h, i) => (
          <div
            key={h.handoff_id || i}
            style={{
              display: 'flex', gap: 6, padding: '2px 0',
              borderBottom: '1px solid rgba(255,255,255,0.04)',
              fontSize: '0.6rem',
            }}
          >
            <span style={{ color: '#4b5563', width: 36, flexShrink: 0 }}>T+{h.offset_seconds}s</span>
            <span style={{ color: handoffColor(h.reason) }}>{h.from_camera_id}</span>
            <span style={{ color: '#4b5563' }}>→</span>
            <span style={{ color: '#9ca3af' }}>{h.to_camera_id}</span>
            <span style={{ color: '#4b5563', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {h.reason || ''}
            </span>
            <span style={{ color: '#6b7280', flexShrink: 0 }}>{Math.round((h.confidence || 0) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
