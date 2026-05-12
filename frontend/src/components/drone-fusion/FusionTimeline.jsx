export default function FusionTimeline({ timeline }) {
  if (!timeline?.entries?.length) return <div style={{ color: '#6b7280', fontSize: 13 }}>No timeline entries.</div>
  return (
    <div>
      <h3>Fusion Timeline ({timeline.entries.length} entries)</h3>
      <div style={{ borderLeft: '2px solid #374151', paddingLeft: 12 }}>
        {timeline.entries.map(entry => (
          <div key={entry.entry_id} style={{ marginBottom: 10, position: 'relative' }}>
            <div style={{ position: 'absolute', left: -18, top: 4, width: 10, height: 10, borderRadius: '50%',
              background: entry.entry_type === 'correlation' ? '#3b82f6' : entry.entry_type === 'handoff' ? '#f59e0b' : '#6b7280' }} />
            <div style={{ fontSize: 12, color: '#9ca3af' }}>{entry.timestamp?.slice(0, 19)}</div>
            <div style={{ fontSize: 13 }}>
              <span style={{ color: '#e5e7eb' }}>{entry.entry_type}</span>
              {entry.source_type && <span style={{ color: '#60a5fa' }}> · {entry.source_type}</span>}
              {entry.confidence != null && <span style={{ color: '#a3e635' }}> · {(entry.confidence * 100).toFixed(1)}%</span>}
            </div>
            {entry.safe_summary && <div style={{ fontSize: 11, color: '#9ca3af' }}>{entry.safe_summary}</div>}
            {entry.simulated && <span style={{ fontSize: 11, color: '#7c3aed' }}>Simulated</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
