function projectPercent(project, latitude, longitude) {
  const pos = project(latitude, longitude)
  return {
    x: parseFloat(String(pos.left).replace('%', '')),
    y: parseFloat(String(pos.top).replace('%', '')),
  }
}

export default function DronePathLayer({ paths, project }) {
  return (
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} viewBox="0 0 100 100" preserveAspectRatio="none">
      {(paths || []).map(path => {
        const points = (path.points || [])
          .map(point => projectPercent(project, point.latitude, point.longitude))
        if (!points.length) return null
        const d = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')
        const latest = points[points.length - 1]
        return (
          <g key={path.drone_id}>
            <path d={d} fill="none" stroke="rgba(245,158,11,0.95)" strokeWidth="0.4" strokeDasharray="1.8 1.2" />
            {points.map((point, index) => (
              <circle key={`${path.drone_id}-${index}`} cx={point.x} cy={point.y} r={index === points.length - 1 ? 0.9 : 0.45} fill={index === points.length - 1 ? '#f97316' : '#fbbf24'} />
            ))}
            <text x={latest.x + 1.2} y={latest.y - 1.2} fontSize="2.5" fill="#fbbf24" fontWeight="700">
              SIM
            </text>
          </g>
        )
      })}
    </svg>
  )
}
