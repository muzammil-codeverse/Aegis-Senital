/**
 * Waypoint list editor for building a simulated patrol route.
 */
import { useState } from 'react'

const DEFAULT_WP = {
  latitude: 30.1575,
  longitude: 71.5249,
  altitude_meters: 40,
  velocity_mps: 5,
  hold_seconds: 0,
  camera_action: 'none',
  label: '',
}

export default function WaypointEditor({ waypoints, onChange }) {
  const [editIdx, setEditIdx] = useState(null)

  function addWaypoint() {
    onChange([...waypoints, { ...DEFAULT_WP, waypoint_id: `wp_${Date.now()}` }])
    setEditIdx(waypoints.length)
  }

  function removeWaypoint(idx) {
    const next = waypoints.filter((_, i) => i !== idx)
    onChange(next)
    setEditIdx(null)
  }

  function updateWaypoint(idx, field, value) {
    const next = waypoints.map((wp, i) =>
      i === idx ? { ...wp, [field]: value } : wp
    )
    onChange(next)
  }

  return (
    <div className="waypoint-editor">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <strong style={{ fontSize: 13 }}>Waypoints ({waypoints.length})</strong>
        <button className="btn btn-sm" onClick={addWaypoint} type="button">+ Add</button>
      </div>

      {waypoints.length === 0 && (
        <div style={{ color: '#777', fontSize: 12, padding: '8px 0' }}>
          No waypoints yet. Add at least 2 to create a mission.
        </div>
      )}

      {waypoints.map((wp, idx) => (
        <div key={wp.waypoint_id || idx} style={{
          border: '1px solid #333',
          borderRadius: 4,
          marginBottom: 6,
          padding: 8,
          background: editIdx === idx ? '#1e2533' : '#161c28',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: '#aaa' }}>
              WP {idx + 1}{wp.label ? ` — ${wp.label}` : ''}
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-sm" type="button" onClick={() => setEditIdx(editIdx === idx ? null : idx)}>
                {editIdx === idx ? 'Collapse' : 'Edit'}
              </button>
              <button className="btn btn-sm btn-danger" type="button" onClick={() => removeWaypoint(idx)}>Remove</button>
            </div>
          </div>

          {editIdx === idx && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 8 }}>
              {['latitude', 'longitude', 'altitude_meters', 'velocity_mps', 'hold_seconds'].map(field => (
                <label key={field} style={{ fontSize: 11 }}>
                  {field.replace(/_/g, ' ')}
                  <input
                    type="number"
                    step="any"
                    value={wp[field]}
                    onChange={e => updateWaypoint(idx, field, parseFloat(e.target.value) || 0)}
                    style={{ display: 'block', width: '100%', marginTop: 2 }}
                  />
                </label>
              ))}
              <label style={{ fontSize: 11, gridColumn: '1/-1' }}>
                label
                <input
                  type="text"
                  value={wp.label || ''}
                  onChange={e => updateWaypoint(idx, 'label', e.target.value)}
                  style={{ display: 'block', width: '100%', marginTop: 2 }}
                />
              </label>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
