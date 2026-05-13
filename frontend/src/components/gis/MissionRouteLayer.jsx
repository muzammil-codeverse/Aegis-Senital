function projectPercent(project, latitude, longitude) {
  const pos = project(latitude, longitude)
  return {
    x: parseFloat(String(pos.left).replace('%', '')),
    y: parseFloat(String(pos.top).replace('%', '')),
  }
}

export default function MissionRouteLayer({ activePaths = [], completedPaths = [], project }) {
  const all = [
    ...(activePaths || []).map(item => ({ ...item, tone: 'active' })),
    ...(completedPaths || []).map(item => ({ ...item, tone: 'completed' })),
  ]
  return (
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} viewBox="0 0 100 100" preserveAspectRatio="none">
      {all.map(path => {
        const points = (path.points || [])
          .map(point => projectPercent(project, point.latitude, point.longitude))
        if (points.length < 2) return null
        const d = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')
        const current = points[Math.max(0, Math.min(points.length - 1, Number(path.current_waypoint_index || 0)))]
        const stroke = path.tone === 'active' ? '#22d3ee' : '#a3a3a3'
        const dash = path.tone === 'active' ? '1.8 1.2' : '0'
        return (
          <g key={`${path.mission_id}-${path.session_id || path.tone}`}>
            <path d={d} fill="none" stroke={stroke} strokeWidth="0.45" strokeDasharray={dash} />
            {current ? (
              <circle cx={current.x} cy={current.y} r={1.0} fill={path.tone === 'active' ? '#22d3ee' : '#cbd5e1'} />
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}
