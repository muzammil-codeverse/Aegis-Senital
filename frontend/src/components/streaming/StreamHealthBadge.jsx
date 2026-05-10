const COLOR_BY_STATUS = {
  healthy: '#52c41a',
  degraded: '#faad14',
  reconnecting: '#1890ff',
  failed: '#ff4d4f',
  stopped: '#8c8c8c',
}

export default function StreamHealthBadge({ status = 'stopped' }) {
  const color = COLOR_BY_STATUS[status] || '#8c8c8c'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 8px',
        borderRadius: 999,
        border: `1px solid ${color}`,
        color,
        fontSize: '0.68rem',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: 0.8,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />
      {status}
    </span>
  )
}
