function projectPercent(project, latitude, longitude) {
  const pos = project(latitude, longitude)
  return {
    x: parseFloat(String(pos.left).replace('%', '')),
    y: parseFloat(String(pos.top).replace('%', '')),
  }
}

export default function HandoffArrowLayer({ handoffs = [], project }) {
  return (
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} viewBox="0 0 100 100" preserveAspectRatio="none">
      {(handoffs || []).map(item => {
        const from = projectPercent(project, item.from?.latitude, item.from?.longitude)
        const to = projectPercent(project, item.to?.latitude, item.to?.longitude)
        const dx = to.x - from.x
        const dy = to.y - from.y
        const length = Math.max(0.001, Math.hypot(dx, dy))
        const ux = dx / length
        const uy = dy / length
        const ax = to.x - (ux * 1.8)
        const ay = to.y - (uy * 1.8)
        return (
          <g key={item.handoff_id}>
            <line x1={from.x} y1={from.y} x2={ax} y2={ay} stroke="#f59e0b" strokeWidth="0.38" strokeDasharray="1.4 1.4" />
            <polygon points={`${to.x},${to.y} ${to.x - uy * 0.8 - ux * 1.2},${to.y + ux * 0.8 - uy * 1.2} ${to.x + uy * 0.8 - ux * 1.2},${to.y - ux * 0.8 - uy * 1.2}`} fill="#f59e0b" />
          </g>
        )
      })}
    </svg>
  )
}
