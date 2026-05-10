function Stat({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: '0.72rem' }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
      <strong style={{ color: '#e5e7eb' }}>{value ?? '—'}</strong>
    </div>
  )
}

export default function StreamStatsPanel({ stats }) {
  if (!stats) return null
  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="panel-header" style={{ marginBottom: 10 }}>
        <div>
          <p className="eyebrow">Stream Stats</p>
          <h2 style={{ fontSize: '0.95rem' }}>Live Telemetry</h2>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 6 }}>
        <Stat label="Decode FPS" value={stats.fps_decode?.toFixed?.(1) ?? stats.fps_decode} />
        <Stat label="Processed FPS" value={stats.fps_processed?.toFixed?.(1) ?? stats.fps_processed} />
        <Stat label="Latency" value={stats.latency_ms != null ? `${stats.latency_ms} ms` : '—'} />
        <Stat label="Queue Depth" value={stats.frame_queue_depth} />
        <Stat label="Dropped Frames" value={stats.dropped_frames_total} />
        <Stat label="Reconnects" value={stats.reconnect_attempts} />
        <Stat label="Preview Clients" value={stats.preview_clients_active} />
      </div>
    </section>
  )
}
