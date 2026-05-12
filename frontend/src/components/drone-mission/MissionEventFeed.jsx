/**
 * Live feed of simulated patrol mission lifecycle events.
 */
const EVENT_COLORS = {
  mission_started: '#3cb371',
  mission_completed: '#4a90d9',
  mission_failed: '#e74c3c',
  mission_cancelled: '#888',
  mission_paused: '#e6a817',
  mission_resumed: '#3cb371',
  waypoint_reached: '#7ec87e',
  simulator_disconnected: '#e74c3c',
  observation_recorded: '#aaa',
}

export default function MissionEventFeed({ events }) {
  if (!events || events.length === 0) {
    return <div style={{ color: '#666', fontSize: 12, padding: 8 }}>No events yet.</div>
  }

  const recent = events.slice(-30).reverse()

  return (
    <div className="mission-event-feed" style={{ maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
      {recent.map((evt, idx) => (
        <div key={evt.event_id || idx} style={{
          padding: '4px 6px',
          borderBottom: '1px solid #1e2535',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-start',
        }}>
          <span style={{ color: '#666', minWidth: 60 }}>{evt.timestamp?.slice(11, 19)}</span>
          <span style={{
            color: EVENT_COLORS[evt.event_type] || '#aaa',
            fontWeight: 600,
            minWidth: 120,
          }}>
            {evt.event_type?.replace(/_/g, ' ')}
          </span>
          <span style={{ color: '#999' }}>{evt.detail || evt.safe_label || ''}</span>
        </div>
      ))}
    </div>
  )
}
