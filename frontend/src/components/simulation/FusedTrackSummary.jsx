const STATUS_COLOR = {
  active: '#52c41a',
  completed: '#1890ff',
  lost: '#ff4d4f',
}

export default function FusedTrackSummary({ fusedTrack = null }) {
  if (!fusedTrack) {
    return (
      <div style={{ color: '#4b5563', fontSize: '0.7rem', textAlign: 'center', padding: '8px 0' }}>
        Fused track not yet available — step through the scenario to build it.
      </div>
    )
  }

  const statusColor = STATUS_COLOR[fusedTrack.status] || '#6b7280'
  const waypointCount = fusedTrack.waypoints?.length || 0
  const camObsCount = fusedTrack.camera_observations?.length || 0
  const droneObsCount = fusedTrack.drone_observations?.length || 0
  const handoffCount = fusedTrack.handoffs?.length || 0

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor }} />
        <span style={{ fontSize: '0.72rem', color: '#d1d5db', fontFamily: 'monospace' }}>
          {String(fusedTrack.track_id || '').slice(0, 20)}
        </span>
        <span style={{ fontSize: '0.65rem', color: statusColor }}>{fusedTrack.status?.toUpperCase()}</span>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: '0.65rem', color: '#9ca3af', marginBottom: 6 }}>
        <span>Actor: <strong style={{ color: '#d1d5db' }}>{fusedTrack.actor_id}</strong></span>
        <span>Confidence: <strong style={{ color: '#52c41a' }}>{Math.round((fusedTrack.confidence || 0) * 100)}%</strong></span>
      </div>

      {/* Source types */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
        {(fusedTrack.source_types || []).map(src => (
          <span key={src} style={{
            fontSize: '0.58rem', padding: '1px 5px', borderRadius: 3,
            background: src === 'drone_camera' ? 'rgba(24,144,255,0.15)' : 'rgba(82,196,26,0.12)',
            color: src === 'drone_camera' ? '#1890ff' : '#52c41a',
            border: `1px solid ${src === 'drone_camera' ? 'rgba(24,144,255,0.25)' : 'rgba(82,196,26,0.2)'}`,
          }}>
            {src.replace(/_/g, ' ')}
          </span>
        ))}
      </div>

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 4, marginBottom: 6 }}>
        {[
          { label: 'Waypoints', value: waypointCount, color: '#d1d5db' },
          { label: 'CCTV obs', value: camObsCount, color: '#52c41a' },
          { label: 'Drone obs', value: droneObsCount, color: '#1890ff' },
          { label: 'Handoffs', value: handoffCount, color: '#fa8c16' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            padding: '4px 6px', borderRadius: 4,
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.06)',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: '0.55rem', color: '#4b5563' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Alert/incident IDs */}
      {fusedTrack.alert_ids?.length > 0 && (
        <div style={{ marginBottom: 4, fontSize: '0.6rem', color: '#6b7280' }}>
          Alerts: {fusedTrack.alert_ids.map(id => (
            <span key={id} style={{ color: '#ff4d4f', fontFamily: 'monospace', marginRight: 4 }}>
              {String(id).slice(0, 16)}
            </span>
          ))}
        </div>
      )}
      {fusedTrack.incident_ids?.length > 0 && (
        <div style={{ fontSize: '0.6rem', color: '#6b7280' }}>
          Incidents: {fusedTrack.incident_ids.map(id => (
            <span key={id} style={{ color: '#fa8c16', fontFamily: 'monospace', marginRight: 4 }}>
              {String(id).slice(0, 16)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
