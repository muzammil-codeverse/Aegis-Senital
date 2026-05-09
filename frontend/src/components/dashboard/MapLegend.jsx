const LEGEND_ITEMS = [
  { color: '#52c41a', label: 'Camera Online' },
  { color: '#fa8c16', label: 'Camera Degraded' },
  { color: '#ff4d4f', label: 'Camera Error / Critical Alert' },
  { color: '#8c8c8c', label: 'Camera Offline' },
  { color: '#ff4d4f33', label: 'Restricted Zone', fill: true },
  { color: '#1890ff33', label: 'Monitored Zone', fill: true },
  { color: '#fa8c1633', label: 'High Priority Zone', fill: true },
  { color: '#52c41a33', label: 'Normal Zone', fill: true },
  { color: '#9b59b655', label: 'Active Incident', fill: true },
  { color: '#fa8c16', label: 'Alert Marker' },
]

export default function MapLegend({ compact = false }) {
  if (compact) {
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 10px', fontSize: '0.6rem', color: '#6b7280' }}>
        {LEGEND_ITEMS.slice(0, 6).map(item => (
          <span key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              display: 'inline-block', width: 10, height: 10,
              borderRadius: item.fill ? 2 : '50%',
              background: item.color,
              border: item.fill ? `1px solid ${item.color.slice(0, 7)}` : 'none',
              flexShrink: 0,
            }} />
            {item.label}
          </span>
        ))}
      </div>
    )
  }

  return (
    <div style={{ padding: '8px 12px', borderTop: '1px solid #1c2535' }}>
      <p style={{ margin: '0 0 5px', fontSize: '0.58rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>Legend</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 12px' }}>
        {LEGEND_ITEMS.map(item => (
          <span key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.62rem', color: '#9ca3af' }}>
            <span style={{
              display: 'inline-block', width: 10, height: 10,
              borderRadius: item.fill ? 2 : '50%',
              background: item.color,
              border: item.fill ? `1px solid ${item.color.slice(0, 7)}` : 'none',
              flexShrink: 0,
            }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  )
}
