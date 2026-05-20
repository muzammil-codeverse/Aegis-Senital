const STATUS_COLOR = {
  planned: '#faad14',
  dispatched: '#1890ff',
  tracking: '#52c41a',
  completed: '#6b7280',
  cancelled: '#ff4d4f',
}

const PHASE_COLOR = {
  dispatch: '#faad14',
  tracking: '#1890ff',
  default: '#9ca3af',
}

function phaseColor(meta) {
  const phase = meta?.phase || 'default'
  return PHASE_COLOR[phase] || PHASE_COLOR.default
}

export default function DroneRoutePanel({ droneRoute = null, droneDispatched = false, dispatchedDroneId = null, unifiedState = null }) {
  if (!droneDispatched && !droneRoute) {
    return (
      <div style={{ color: '#4b5563', fontSize: '0.7rem', textAlign: 'center', padding: '10px 0' }}>
        DRONE-ALPHA awaiting dispatch — weapon event will trigger.
      </div>
    )
  }

  const statusColor = STATUS_COLOR[droneRoute?.status] || '#6b7280'
  const waypoints = droneRoute?.waypoints || []
  const cameraFeedUri = droneRoute?.metadata?.camera_feed_uri || unifiedState?.camera_feed_uri || ''
  const providerConnected = unifiedState?.provider_state?.simulator_connected ?? false

  return (
    <div>
      {/* Route header */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
        <strong style={{ fontSize: '0.72rem', color: '#d1d5db' }}>{dispatchedDroneId || droneRoute?.drone_id || 'DRONE-ALPHA'}</strong>
        <span style={{ fontSize: '0.65rem', color: statusColor }}>{droneRoute?.status?.toUpperCase() || 'DISPATCHED'}</span>
        {droneRoute?.mission_id && (
          <span style={{ fontSize: '0.58rem', color: '#4b5563', fontFamily: 'monospace' }}>{droneRoute.mission_id}</span>
        )}
        {droneRoute?.linked_actor_id && (
          <span style={{ fontSize: '0.6rem', color: '#fa8c16' }}>Tracking: {droneRoute.linked_actor_id}</span>
        )}
      </div>

      {/* Provider + feed status */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 6, fontSize: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ color: providerConnected ? '#52c41a' : '#4b5563' }}>
          AirSim: {providerConnected ? 'connected' : 'disconnected'}
        </span>
        {cameraFeedUri && (
          <span style={{ color: '#6b7280', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 200 }}>
            Feed: {cameraFeedUri}
          </span>
        )}
      </div>

      {/* Waypoint list */}
      {waypoints.length > 0 ? (
        <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
          {waypoints.map((wp, i) => {
            const col = phaseColor(wp.metadata)
            const isLast = i === waypoints.length - 1
            return (
              <li key={wp.waypoint_id || i} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', marginBottom: 2 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: 10 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '2px', background: col, transform: 'rotate(45deg)' }} />
                  {!isLast && <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.1)' }} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '0.6rem', color: '#4b5563' }}>T+{wp.offset_seconds}s</span>
                    <span style={{ fontSize: '0.65rem', color: col }}>
                      {wp.metadata?.description || wp.zone_name || wp.zone_id || '—'}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.58rem', color: '#4b5563', marginTop: 1, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <span>z={Math.round(wp.location?.z ?? 0)}m</span>
                    <span>({Math.round(wp.location?.x ?? 0)}, {Math.round(wp.location?.y ?? 0)})</span>
                    <span>{Math.round((wp.confidence || 0) * 100)}%</span>
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      ) : (
        <div style={{ fontSize: '0.65rem', color: '#4b5563' }}>No waypoints in route.</div>
      )}

      {droneRoute?.metadata?.airsim_ready === false && (
        <div style={{ marginTop: 6, fontSize: '0.58rem', color: '#4b5563', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 4 }}>
          Provider: cosys_airsim · Simulation route (deterministic)
        </div>
      )}
    </div>
  )
}
