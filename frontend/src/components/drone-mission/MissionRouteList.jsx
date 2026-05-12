/**
 * Displays the list of saved simulated patrol missions.
 */
export default function MissionRouteList({ missions, onSelect, onDelete, selectedId }) {
  if (!missions || missions.length === 0) {
    return <div style={{ color: '#666', fontSize: 12, padding: 8 }}>No simulated patrol missions yet.</div>
  }

  return (
    <div className="mission-route-list">
      {missions.map(m => (
        <div
          key={m.mission_id}
          style={{
            border: `1px solid ${selectedId === m.mission_id ? '#4a90d9' : '#333'}`,
            borderRadius: 4,
            padding: '8px 10px',
            marginBottom: 6,
            cursor: 'pointer',
            background: selectedId === m.mission_id ? '#1a2840' : '#12182a',
          }}
          onClick={() => onSelect && onSelect(m)}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</div>
              <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
                {m.waypoints?.length ?? 0} waypoints &middot; {m.route_type} &middot; {m.status}
              </div>
              {m.estimated_distance_meters != null && (
                <div style={{ fontSize: 11, color: '#888' }}>
                  ~{(m.estimated_distance_meters / 1000).toFixed(2)} km &middot;
                  ~{Math.ceil((m.estimated_duration_seconds || 0) / 60)} min
                </div>
              )}
            </div>
            <button
              className="btn btn-sm btn-danger"
              type="button"
              onClick={e => { e.stopPropagation(); onDelete && onDelete(m.mission_id) }}
              disabled={!['draft', 'cancelled'].includes(m.status)}
            >
              Del
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
