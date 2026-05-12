import { useEffect, useState } from 'react'

export default function CameraGeoProfileDrawer({ open, profile, canWrite, onClose, onSave }) {
  const [form, setForm] = useState({})
  useEffect(() => {
    if (profile) setForm({ ...profile })
  }, [profile])
  if (!open || !profile) return null
  return (
    <aside className="detail-drawer" style={{ maxWidth: 360 }}>
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Camera coverage</p>
          <h2>{form.name || form.camera_id}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose}>x</button>
      </div>
      <div className="drawer-grid" style={{ fontSize: '0.75rem' }}>
        <span>Latitude</span>
        <input value={form.latitude ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, latitude: e.target.value }))} />
        <span>Longitude</span>
        <input value={form.longitude ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, longitude: e.target.value }))} />
        <span>Altitude (m)</span>
        <input value={form.altitude_meters ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, altitude_meters: e.target.value }))} />
        <span>Heading °</span>
        <input value={form.heading_degrees ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, heading_degrees: e.target.value }))} />
        <span>FOV °</span>
        <input value={form.fov_degrees ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, fov_degrees: e.target.value }))} />
        <span>Coverage radius (m)</span>
        <input value={form.coverage_radius_meters ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, coverage_radius_meters: e.target.value }))} />
        <span>Region</span>
        <input value={form.region ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, region: e.target.value }))} />
        <span>Floor</span>
        <input value={form.floor_level ?? ''} disabled={!canWrite} onChange={e => setForm(f => ({ ...f, floor_level: e.target.value }))} />
      </div>
      {canWrite ? (
        <div className="button-row" style={{ marginTop: 12 }}>
          <button type="button" className="primary-button" onClick={() => onSave?.(form)}>Save profile</button>
        </div>
      ) : (
        <p className="muted" style={{ marginTop: 12 }}>Operator review: edits require gis:write and camera scope.</p>
      )}
    </aside>
  )
}
