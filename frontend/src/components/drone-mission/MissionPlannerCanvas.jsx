function projectWaypoint(waypoints, latitude, longitude) {
  const lats = waypoints.map(item => Number(item.latitude || 0))
  const lons = waypoints.map(item => Number(item.longitude || 0))
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const x = ((Number(longitude) - minLon) / ((maxLon - minLon) || 1e-9)) * 100
  const y = 100 - (((Number(latitude) - minLat) / ((maxLat - minLat) || 1e-9)) * 100)
  return { x: Math.max(2, Math.min(98, x)), y: Math.max(2, Math.min(98, y)) }
}

export default function MissionPlannerCanvas({ mission, session, telemetry, selectedPreset }) {
  const waypoints = mission?.waypoints || []
  const points = waypoints.map(item => projectWaypoint(waypoints, item.latitude, item.longitude))
  const route = points.map((item, index) => `${index === 0 ? 'M' : 'L'}${item.x},${item.y}`).join(' ')
  const activeWaypointIndex = Number(session?.current_waypoint_index || 0)
  const activeWaypoint = points[activeWaypointIndex] || points[points.length - 1]

  return (
    <div className="mission-planner-canvas" style={{
      background: '#0d1320',
      border: '1px solid #2a3550',
      borderRadius: 6,
      minHeight: 240,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      padding: 16,
    }}>
      {waypoints.length === 0 ? (
        <div style={{ color: '#555', fontSize: 13 }}>
          Add waypoints to visualize the simulated patrol route
        </div>
      ) : (
        <div style={{ width: '100%' }}>
          <svg width="100%" height="140" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ border: '1px solid #1f2937', borderRadius: 6 }}>
            <defs>
              <pattern id="mission-grid" width="10" height="10" patternUnits="userSpaceOnUse">
                <path d="M10 0 L0 0 0 10" fill="none" stroke="#223049" strokeWidth="0.3" />
              </pattern>
            </defs>
            <rect width="100" height="100" fill="url(#mission-grid)" />
            <path d={route} fill="none" stroke="#f59e0b" strokeWidth="1.2" strokeDasharray="2.2 1.4" />
            {points.map((point, index) => (
              <circle
                key={`${mission?.mission_id || 'm'}-${index}`}
                cx={point.x}
                cy={point.y}
                r={index === activeWaypointIndex ? 2.3 : 1.4}
                fill={index === activeWaypointIndex ? '#f97316' : '#fde68a'}
              />
            ))}
            {activeWaypoint ? (
              <g>
                <circle cx={activeWaypoint.x} cy={activeWaypoint.y} r="3.2" fill="none" stroke="#22d3ee" strokeWidth="0.8" />
                <text x={activeWaypoint.x + 1.8} y={Math.max(4, activeWaypoint.y - 2)} fontSize="3" fill="#7dd3fc">
                  Current WP
                </text>
              </g>
            ) : null}
          </svg>
          <div style={{ fontSize: 12, color: '#7ec87e', marginBottom: 8 }}>
            Candidate patrol route - {waypoints.length} waypoints
          </div>
          <div style={{ fontSize: 11, color: '#888', lineHeight: 1.8 }}>
            {waypoints.map((wp, i) => (
              <div key={wp.waypoint_id || i}>
                WP {i + 1}: {wp.latitude?.toFixed(5)}, {wp.longitude?.toFixed(5)} @ {wp.altitude_meters}m
                {wp.label ? ` - ${wp.label}` : ''}
              </div>
            ))}
          </div>
          {session?.status === 'executing' ? (
            <div style={{ marginTop: 8, color: '#3cb371', fontSize: 11 }}>
              Simulated patrol in progress - waypoint {session.current_waypoint_index + 1}/{session.total_waypoints}
            </div>
          ) : null}
          {selectedPreset ? (
            <div style={{ marginTop: 6, color: '#93c5fd', fontSize: 11 }}>
              Demo outcome: {selectedPreset.expected_demo_outcome || 'Candidate cross-source observation.'}
            </div>
          ) : null}
          {telemetry?.length > 0 ? (
            <div style={{ marginTop: 4, color: '#aaa', fontSize: 11 }}>
              {telemetry.length} telemetry points recorded
            </div>
          ) : null}
        </div>
      )}
      <div style={{ position: 'absolute', bottom: 6, right: 10, fontSize: 10, color: '#3a6a3a' }}>
        SIMULATION ONLY
      </div>
      <div style={{ position: 'absolute', bottom: 6, left: 10, fontSize: 10, color: '#38bdf8' }}>
        simulated_geo=true
      </div>
    </div>
  )
}
