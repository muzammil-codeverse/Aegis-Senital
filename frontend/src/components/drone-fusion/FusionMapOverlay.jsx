export default function FusionMapOverlay({ correlations = [], handoffs = [], observations = [] }) {
  const hasGeo = obs => !obs.geo_missing && obs.latitude != null && obs.longitude != null
  const obsById = Object.fromEntries(observations.map(item => [item.observation_id, item]))

  const corrLines = correlations.filter(corr => {
    const a = obsById[corr.primary_observation_id]
    const b = obsById[corr.matched_observation_id]
    return a && b && hasGeo(a) && hasGeo(b)
  }).map(corr => ({
    type: 'correlation_line',
    correlation_id: corr.correlation_id,
    from: { lat: obsById[corr.primary_observation_id].latitude, lon: obsById[corr.primary_observation_id].longitude },
    to: { lat: obsById[corr.matched_observation_id].latitude, lon: obsById[corr.matched_observation_id].longitude },
    confidence: corr.confidence,
    review_status: corr.review_status,
    source_pair: corr.source_pair,
    label: `${corr.source_pair?.join(' <-> ')} - ${(Number(corr.confidence || 0) * 100).toFixed(0)}%`,
    color: corr.review_status === 'accepted' ? '#34d399' : corr.review_status === 'rejected' ? '#f87171' : '#60a5fa',
  }))

  if (!corrLines.length && !handoffs.length) {
    return (
      <div style={{ color: '#6b7280', fontSize: 13, padding: 8 }}>
        No geospatially-resolved fusion items to overlay. (Unauthorized or geo-missing endpoints are hidden.)
      </div>
    )
  }

  return (
    <div style={{ fontSize: 12, border: '1px solid #374151', borderRadius: 6, padding: 8 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>Map Overlay Contract - Fusion Lines ({corrLines.length})</div>
      {corrLines.map(line => (
        <div key={line.correlation_id} style={{ marginBottom: 4, display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ width: 24, height: 3, background: line.color, display: 'inline-block', borderRadius: 2 }} />
          <span style={{ color: '#9ca3af' }}>{line.label}</span>
          <span style={{ color: '#6b7280' }}>
            [{line.from.lat.toFixed(4)},{line.from.lon.toFixed(4)}]{' -> '}[{line.to.lat.toFixed(4)},{line.to.lon.toFixed(4)}]
          </span>
        </div>
      ))}
      <div style={{ fontWeight: 600, marginTop: 8, marginBottom: 4 }}>Fixed-camera handoff arrows ({handoffs.length})</div>
      {handoffs.map(handoff => (
        <div key={handoff.handoff_id} style={{ marginBottom: 4, color: '#fbbf24' }}>
          {handoff.from_source_id}{' -> '}{handoff.to_source_id} ({(Number(handoff.confidence || 0) * 100).toFixed(0)}%)
        </div>
      ))}
      <div style={{ color: '#6b7280', marginTop: 4, fontSize: 11 }}>
        Unauthorized source locations are not displayed. Simulated drone observations are labelled.
      </div>
    </div>
  )
}
