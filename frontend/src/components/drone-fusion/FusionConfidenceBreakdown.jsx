export default function FusionConfidenceBreakdown({ breakdown, confidence }) {
  if (!breakdown) return null
  const rows = [
    { label: 'Time', value: breakdown.time_score },
    { label: 'Geo', value: breakdown.geo_score },
    { label: 'Appearance', value: breakdown.appearance_score },
    { label: 'Event Type', value: breakdown.event_type_score },
    { label: 'Mission Context', value: breakdown.mission_context_score },
  ]
  return (
    <div style={{ fontSize: 12, border: '1px solid #374151', borderRadius: 6, padding: 8 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        Confidence: {(confidence * 100).toFixed(1)}%
      </div>
      {rows.map(r => (
        <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
          <span style={{ color: '#9ca3af' }}>{r.label}</span>
          <span>{r.value != null ? (r.value * 100).toFixed(1) + '%' : '—'}</span>
        </div>
      ))}
    </div>
  )
}
