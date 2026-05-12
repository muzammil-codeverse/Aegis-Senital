/**
 * Map canvas placeholder for visualising simulated patrol waypoints.
 * Full GIS map integration is in MapCommandCenter (drone_mission_routes layer).
 */
export default function MissionPlannerCanvas({ mission, session, telemetry }) {
  const waypoints = mission?.waypoints || []

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
          Add waypoints to visualise the simulated patrol route
        </div>
      ) : (
        <div style={{ width: '100%' }}>
          <div style={{ fontSize: 12, color: '#7ec87e', marginBottom: 8 }}>
            Candidate patrol route — {waypoints.length} waypoints
          </div>
          <div style={{ fontSize: 11, color: '#888', lineHeight: 1.8 }}>
            {waypoints.map((wp, i) => (
              <div key={wp.waypoint_id || i}>
                WP {i + 1}: {wp.latitude?.toFixed(5)}, {wp.longitude?.toFixed(5)} @ {wp.altitude_meters}m
                {wp.label ? ` — ${wp.label}` : ''}
              </div>
            ))}
          </div>
          {session?.status === 'executing' && (
            <div style={{ marginTop: 8, color: '#3cb371', fontSize: 11 }}>
              Simulated patrol in progress — waypoint {session.current_waypoint_index + 1}/{session.total_waypoints}
            </div>
          )}
          {telemetry?.length > 0 && (
            <div style={{ marginTop: 4, color: '#aaa', fontSize: 11 }}>
              {telemetry.length} telemetry points recorded
            </div>
          )}
        </div>
      )}
      <div style={{ position: 'absolute', bottom: 6, right: 10, fontSize: 10, color: '#3a6a3a' }}>
        SIMULATION ONLY
      </div>
    </div>
  )
}
