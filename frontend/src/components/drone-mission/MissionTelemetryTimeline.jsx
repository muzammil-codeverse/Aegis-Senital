/**
 * Displays a scrollable timeline of simulated patrol telemetry points.
 */
export default function MissionTelemetryTimeline({ telemetry }) {
  if (!telemetry || telemetry.length === 0) {
    return <div style={{ color: '#666', fontSize: 12, padding: 8 }}>No telemetry recorded yet.</div>
  }

  const recent = telemetry.slice(-20).reverse()
  const latest = telemetry[telemetry.length - 1] || null
  const progress = Math.max(0, Math.min(100, Number(latest?.progress_percent || 0)))

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: '#93c5fd' }}>
          Live route progress: {progress.toFixed(1)}% complete
        </div>
        <div style={{ height: 6, borderRadius: 8, background: '#1f2937', marginTop: 4, overflow: 'hidden' }}>
          <div style={{ width: `${progress}%`, height: '100%', background: 'linear-gradient(90deg, #22d3ee, #60a5fa)' }} />
        </div>
      </div>
      <div className="telemetry-timeline" style={{ maxHeight: 200, overflowY: 'auto', fontSize: 11 }}>
        {recent.map((pt, idx) => (
          <div key={pt.telemetry_id || idx} style={{
            padding: '4px 6px',
            borderBottom: '1px solid #1e2535',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr 1fr',
            gap: 4,
          }}>
            <span style={{ color: '#888' }}>{pt.timestamp?.slice(11, 19)}</span>
            <span>WP {pt.current_waypoint_index}</span>
            <span>{(pt.progress_percent || 0).toFixed(1)}%</span>
            <span style={{ color: '#5aafea' }}>
              {pt.latitude != null ? `${pt.latitude.toFixed(4)},${pt.longitude?.toFixed(4)}` : 'NED'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
