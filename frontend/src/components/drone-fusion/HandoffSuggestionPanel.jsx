export default function HandoffSuggestionPanel({ handoffs = [] }) {
  if (!handoffs.length) return <div style={{ color: '#6b7280', fontSize: 13 }}>No handoff suggestions.</div>
  return (
    <div>
      <h3>Handoff Suggestions ({handoffs.length})</h3>
      {handoffs.map(h => (
        <div key={h.handoff_id} style={{ border: '1px solid #374151', borderRadius: 6, padding: 8, marginBottom: 6, fontSize: 13 }}>
          <div style={{ color: '#60a5fa' }}>{h.from_source_type} ({h.from_source_id}) → {h.to_source_type} ({h.to_source_id})</div>
          <div style={{ color: '#9ca3af', fontSize: 12 }}>{h.safe_summary}</div>
          <div style={{ fontSize: 12, marginTop: 2 }}>
            Confidence: <strong>{(h.confidence * 100).toFixed(1)}%</strong>
            {' · '}Reason: {h.reason}
          </div>
          <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 2 }}>Operator review required</div>
        </div>
      ))}
    </div>
  )
}
