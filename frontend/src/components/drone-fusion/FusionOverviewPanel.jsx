export default function FusionOverviewPanel({ correlations = [], handoffs = [], observations = [] }) {
  const pending = correlations.filter(c => c.review_status === 'pending').length
  const accepted = correlations.filter(c => c.review_status === 'accepted').length
  const rejected = correlations.filter(c => c.review_status === 'rejected').length
  const avgConf = correlations.length
    ? (correlations.reduce((s, c) => s + (c.confidence || 0), 0) / correlations.length * 100).toFixed(1)
    : '—'

  const card = (label, value, color) => (
    <div style={{ background: '#1f2937', borderRadius: 8, padding: '10px 16px', flex: 1, minWidth: 120 }}>
      <div style={{ fontSize: 12, color: '#9ca3af' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || '#f9fafb' }}>{value}</div>
    </div>
  )

  return (
    <div>
      <div style={{ fontSize: 11, color: '#f59e0b', marginBottom: 8 }}>
        ⚠ All fusion results are candidate observations requiring operator review. No identity or guilt confirmation.
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {card('Observations', observations.length, '#60a5fa')}
        {card('Correlations', correlations.length, '#a3e635')}
        {card('Pending Reviews', pending, '#f59e0b')}
        {card('Accepted', accepted, '#34d399')}
        {card('Rejected', rejected, '#f87171')}
        {card('Avg Confidence', avgConf + '%', '#c084fc')}
        {card('Handoffs', handoffs.length, '#fb923c')}
      </div>
    </div>
  )
}
