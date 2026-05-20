// 2D SVG grid visualization of suspect path waypoints.
// Coordinate system: city grid 0-500 x 0-350. Suspect moves left→right, top→bottom.

const ZONE_COLORS = {
  zone_financial: '#ff4d4f',
  zone_market: '#fa8c16',
  zone_roads: '#faad14',
  zone_parking: '#52c41a',
  zone_alley: '#1890ff',
  zone_gate: '#722ed1',
}

function zoneColor(zoneId) {
  return ZONE_COLORS[zoneId] || '#6b7280'
}

// Map real coords (0-500, 0-350) into SVG viewport (0-460, 0-280)
function project(x, y, vw = 460, vh = 280, maxX = 500, maxY = 350) {
  return {
    sx: Math.round((x / maxX) * vw),
    sy: Math.round((y / maxY) * vh),
  }
}

export default function SuspectPathMap({ waypoints = [], droneWaypoints = [], runId = null }) {
  const suspectPts = waypoints.filter(w => w.entity_type === 'suspect')
  const dronePts = droneWaypoints.length > 0 ? droneWaypoints : waypoints.filter(w => w.entity_type === 'drone')

  const suspectProj = suspectPts.map(w => ({ ...project(w.location?.x ?? 0, w.location?.y ?? 0), ...w }))
  const droneProj = dronePts.map(w => ({ ...project(w.location?.x ?? 0, w.location?.y ?? 0), ...w }))

  const suspectPolyline = suspectProj.map(p => `${p.sx},${p.sy}`).join(' ')
  const dronePolyline = droneProj.map(p => `${p.sx},${p.sy}`).join(' ')

  return (
    <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 6, padding: 8, border: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ fontSize: '0.65rem', color: '#6b7280', marginBottom: 6, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 20, height: 2, background: '#ff4d4f', display: 'inline-block' }} />
          Suspect path
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 20, height: 0, background: '#1890ff', display: 'inline-block', borderTop: '2px dashed #1890ff' }} />
          DRONE-ALPHA route
        </span>
        {runId && <span style={{ color: '#4b5563' }}>Run: {String(runId).slice(0, 12)}</span>}
      </div>
      <svg
        viewBox="0 0 460 280"
        style={{ width: '100%', height: 180, display: 'block' }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Grid background */}
        <rect width="460" height="280" fill="rgba(255,255,255,0.02)" rx="4" />
        {[0, 1, 2, 3, 4].map(i => (
          <line key={`vg${i}`} x1={i * 115} y1="0" x2={i * 115} y2="280" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
        ))}
        {[0, 1, 2, 3, 4].map(i => (
          <line key={`hg${i}`} x1="0" y1={i * 70} x2="460" y2={i * 70} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
        ))}

        {/* Suspect path polyline */}
        {suspectPolyline && (
          <polyline
            points={suspectPolyline}
            fill="none"
            stroke="#ff4d4f"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.7"
          />
        )}

        {/* Drone route polyline */}
        {dronePolyline && (
          <polyline
            points={dronePolyline}
            fill="none"
            stroke="#1890ff"
            strokeWidth="2"
            strokeDasharray="6,4"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.6"
          />
        )}

        {/* Suspect waypoint nodes */}
        {suspectProj.map((pt, i) => {
          const isFirst = i === 0
          const isLast = i === suspectProj.length - 1
          const color = zoneColor(pt.zone_id)
          return (
            <g key={pt.waypoint_id || i}>
              <circle
                cx={pt.sx} cy={pt.sy}
                r={isFirst || isLast ? 6 : 4}
                fill={color}
                stroke="#0d1117"
                strokeWidth="1.5"
                opacity="0.9"
              />
              {(isFirst || isLast) && (
                <text x={pt.sx + 8} y={pt.sy + 4} fontSize="8" fill={color} opacity="0.85">
                  {isFirst ? 'START' : 'END'}
                </text>
              )}
              <title>T+{pt.offset_seconds}s · {pt.zone_name || pt.zone_id} · {String(pt.source_id || '').slice(0, 12)}</title>
            </g>
          )
        })}

        {/* Drone waypoint nodes */}
        {droneProj.map((pt, i) => (
          <g key={pt.waypoint_id || `d${i}`}>
            <rect
              x={pt.sx - 4} y={pt.sy - 4}
              width="8" height="8"
              fill="#1890ff"
              stroke="#0d1117"
              strokeWidth="1.5"
              opacity="0.85"
              transform={`rotate(45 ${pt.sx} ${pt.sy})`}
            />
            <title>DRONE T+{pt.offset_seconds}s · {pt.zone_name || pt.zone_id}</title>
          </g>
        ))}
      </svg>

      {/* Waypoint legend table */}
      {suspectProj.length > 0 && (
        <div style={{ marginTop: 6, maxHeight: 80, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.6rem', color: '#6b7280' }}>
            <tbody>
              {suspectProj.map((pt, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '1px 4px', color: zoneColor(pt.zone_id), width: 40 }}>T+{pt.offset_seconds}s</td>
                  <td style={{ padding: '1px 4px', color: '#9ca3af' }}>{pt.source_id || '—'}</td>
                  <td style={{ padding: '1px 4px', color: '#4b5563' }}>{pt.zone_name || pt.zone_id || '—'}</td>
                  <td style={{ padding: '1px 4px', textAlign: 'right' }}>{Math.round((pt.confidence || 0) * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {suspectPts.length === 0 && (
        <div style={{ textAlign: 'center', color: '#4b5563', fontSize: '0.7rem', padding: '12px 0' }}>
          No suspect path data — start a scenario run.
        </div>
      )}
    </div>
  )
}
