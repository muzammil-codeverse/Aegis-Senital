const DEMO_SCENARIO = {
  title: 'Bank Robbery Response — Synthetic Scenario',
  runId: 'DEMO-RUN-001',
  observations: [
    { source: 'CAM-BANK-01', type: 'Person detected exiting bank', time: 'T+00:12', confidence: 0.91 },
    { source: 'CAM-MARKET-03', type: 'Possible suspect crossing road', time: 'T+01:47', confidence: 0.84 },
    { source: 'DRONE-ALPHA', type: 'Aerial observation — target moving NW', time: 'T+02:30', confidence: 0.78 },
    { source: 'CAM-PARKING-02', type: 'Vehicle matching description', time: 'T+03:15', confidence: 0.72 },
  ],
  handoffs: [
    { from: 'CAM-BANK-01', to: 'CAM-MARKET-03', at: 'T+01:30', confidence: 0.88 },
    { from: 'CAM-MARKET-03', to: 'DRONE-ALPHA', at: 'T+02:10', confidence: 0.81 },
    { from: 'DRONE-ALPHA', to: 'CAM-PARKING-02', at: 'T+03:00', confidence: 0.76 },
  ],
  summary: 'Synthetic fusion of 4 camera and 1 drone observation across a 3-min simulated bank robbery response. Suspect path tracked from bank exit to parking zone. All outputs are candidate observations requiring operator review.',
}

export default function FusionOverviewPanel({ correlations = [], handoffs = [], observations = [] }) {
  const pending = correlations.filter(c => c.review_status === 'pending').length
  const accepted = correlations.filter(c => c.review_status === 'accepted').length
  const rejected = correlations.filter(c => c.review_status === 'rejected').length
  const avgConf = correlations.length
    ? (correlations.reduce((s, c) => s + (c.confidence || 0), 0) / correlations.length * 100).toFixed(1)
    : '—'

  const isEmpty = observations.length === 0 && correlations.length === 0 && handoffs.length === 0

  const card = (label, value, color) => (
    <div style={{ background: '#1f2937', borderRadius: 8, padding: '10px 16px', flex: 1, minWidth: 120 }}>
      <div style={{ fontSize: 12, color: '#9ca3af' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || '#f9fafb' }}>{value}</div>
    </div>
  )

  return (
    <div>
      <div style={{ fontSize: 11, color: '#f59e0b', marginBottom: 8 }}>
        All fusion results are candidate observations requiring operator review. No identity or guilt confirmation.
      </div>

      {isEmpty ? (
        <div style={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{ background: '#1d4ed8', borderRadius: 4, padding: '2px 8px', fontSize: 10, fontWeight: 700, color: '#93c5fd', textTransform: 'uppercase' }}>
              Synthetic Scenario Fusion
            </span>
            <span style={{ fontSize: 11, color: '#6b7280' }}>{DEMO_SCENARIO.runId}</span>
          </div>
          <h3 style={{ fontSize: 14, fontWeight: 700, color: '#f9fafb', marginBottom: 6 }}>{DEMO_SCENARIO.title}</h3>
          <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 12 }}>{DEMO_SCENARIO.summary}</p>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
              Fused Observations
            </div>
            {DEMO_SCENARIO.observations.map((obs, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0', borderBottom: '1px solid #1f2937', fontSize: 12 }}>
                <span style={{ background: '#1e3a5f', borderRadius: 3, padding: '1px 6px', color: '#60a5fa', fontWeight: 600, flexShrink: 0 }}>{obs.source}</span>
                <span style={{ color: '#d1d5db', flex: 1 }}>{obs.type}</span>
                <span style={{ color: '#6b7280', flexShrink: 0 }}>{obs.time}</span>
                <span style={{ color: '#a3e635', flexShrink: 0 }}>{(obs.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
              Camera-to-Drone Handoff Timeline
            </div>
            {DEMO_SCENARIO.handoffs.map((h, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0', fontSize: 12 }}>
                <span style={{ color: '#fb923c', fontWeight: 600, flexShrink: 0 }}>{h.from}</span>
                <span style={{ color: '#6b7280' }}>→</span>
                <span style={{ color: '#34d399', fontWeight: 600 }}>{h.to}</span>
                <span style={{ color: '#6b7280', flex: 1, textAlign: 'right' }}>{h.at}</span>
                <span style={{ color: '#c084fc', flexShrink: 0 }}>conf {(h.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, padding: '8px 12px', background: '#1f2937', borderRadius: 6, fontSize: 11, color: '#6b7280' }}>
            No live fusion is active. Start an exhibition scenario from the dashboard to generate real fusion observations.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          {card('Observations', observations.length, '#60a5fa')}
          {card('Correlations', correlations.length, '#a3e635')}
          {card('Pending Reviews', pending, '#f59e0b')}
          {card('Accepted', accepted, '#34d399')}
          {card('Rejected', rejected, '#f87171')}
          {card('Avg Confidence', avgConf + '%', '#c084fc')}
          {card('Handoffs', handoffs.length, '#fb923c')}
        </div>
      )}

    </div>
  )
}
