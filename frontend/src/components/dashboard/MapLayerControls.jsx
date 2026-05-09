const LAYERS = [
  { id: 'cameras',     label: 'Cameras' },
  { id: 'zones',       label: 'Zones' },
  { id: 'geofences',   label: 'Geofences' },
  { id: 'connections', label: 'Connections' },
  { id: 'handoffs',    label: 'Handoffs' },
  { id: 'incidents',   label: 'Incidents' },
  { id: 'alerts',      label: 'Alerts' },
  { id: 'heatmap',     label: 'Heatmap' },
  { id: 'fov',         label: 'FOV' },
]

export default function MapLayerControls({ layers, onToggle }) {
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', padding: '4px 8px' }}>
      {LAYERS.map(layer => {
        const active = layers[layer.id] !== false
        return (
          <button
            key={layer.id}
            onClick={() => onToggle(layer.id)}
            style={{
              fontSize: '0.6rem',
              padding: '2px 7px',
              borderRadius: 3,
              border: `1px solid ${active ? '#1890ff' : '#374151'}`,
              background: active ? '#1890ff18' : 'none',
              color: active ? '#1890ff' : '#4b5563',
              cursor: 'pointer',
            }}
          >
            {layer.label}
          </button>
        )
      })}
    </div>
  )
}
