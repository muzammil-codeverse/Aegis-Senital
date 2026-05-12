/**
 * Shows current execution status of an active simulated patrol session.
 */
export default function MissionStatusPanel({ session }) {
  if (!session) {
    return (
      <div style={{ color: '#666', fontSize: 12, padding: 8 }}>
        No active mission session.
      </div>
    )
  }

  const statusColor = {
    executing: '#3cb371',
    paused: '#e6a817',
    completed: '#4a90d9',
    failed: '#e74c3c',
    cancelled: '#888',
    draft: '#666',
  }[session.status] || '#aaa'

  return (
    <div className="mission-status-panel" style={{ fontSize: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <span style={{
          background: statusColor,
          color: '#fff',
          borderRadius: 3,
          padding: '2px 8px',
          fontWeight: 700,
          fontSize: 11,
          textTransform: 'uppercase',
        }}>
          {session.status}
        </span>
        <span style={{ color: '#888' }}>Session: {session.session_id}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
        <div><span style={{ color: '#888' }}>Progress:</span> {(session.progress_percent || 0).toFixed(1)}%</div>
        <div><span style={{ color: '#888' }}>Waypoints:</span> {session.waypoints_reached || 0} / {session.total_waypoints || 0}</div>
        <div><span style={{ color: '#888' }}>Telemetry pts:</span> {session.telemetry_count || 0}</div>
        <div><span style={{ color: '#888' }}>Events:</span> {session.event_count || 0}</div>
      </div>

      {session.last_error && (
        <div style={{ color: '#e74c3c', marginTop: 6, fontSize: 11 }}>
          Error: {session.last_error}
        </div>
      )}

      <div style={{ marginTop: 6, color: '#5a7a5a', fontSize: 10 }}>
        Simulated aerial patrol — operator review required
      </div>
    </div>
  )
}
