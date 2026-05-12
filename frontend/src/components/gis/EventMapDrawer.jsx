export default function EventMapDrawer({ open, marker, onClose }) {
  if (!open || !marker) return null
  return (
    <aside className="detail-drawer" style={{ maxWidth: 360 }}>
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Candidate event location</p>
          <h2>{marker.event_type}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose}>x</button>
      </div>
      <div className="drawer-grid" style={{ fontSize: '0.75rem' }}>
        <span>Source</span><strong>{marker.source_type}</strong>
        <span>Severity</span><strong>{marker.severity}</strong>
        <span>Camera</span><strong>{marker.camera_id || 'N/A'}</strong>
        <span>Time</span><strong>{marker.timestamp}</strong>
        <span>Operator review</span><strong>{marker.operator_review_required ? 'required' : 'optional'}</strong>
      </div>
      <p className="muted" style={{ marginTop: 10 }}>{marker.title}</p>
    </aside>
  )
}
