/**
 * OpenVocabStatusPanel — shows scanner enabled/disabled state, adapter
 * availability, active prompt count, and key metrics.
 */
export default function OpenVocabStatusPanel({ status, loading }) {
  if (loading && !status) {
    return (
      <div className="panel" style={{ padding: 16 }}>
        <p style={{ color: '#6b7280', fontSize: '0.78rem' }}>Loading scanner status…</p>
      </div>
    )
  }

  const adapterStatus = status?.item?.adapter || {}
  const metricsData = status?.item?.metrics || {}
  const enabled = status?.item?.enabled !== false
  const adapterAvailable = adapterStatus.available === true
  const reason = adapterStatus.reason

  const metricRows = [
    { label: 'Scans Requested', value: metricsData.open_vocab_scans_requested ?? 0 },
    { label: 'Scans Completed', value: metricsData.open_vocab_scans_completed ?? 0 },
    { label: 'Threats Found', value: metricsData.open_vocab_threats_found ?? 0 },
    { label: 'Active Prompts', value: metricsData.open_vocab_prompts_active ?? 0 },
    { label: 'Avg Latency (ms)', value: metricsData.open_vocab_scan_latency_ms_avg != null ? metricsData.open_vocab_scan_latency_ms_avg.toFixed(1) : '—' },
    { label: 'Queue Rejected', value: metricsData.open_vocab_scan_queue_rejected ?? 0 },
    { label: 'Scans Failed', value: metricsData.open_vocab_scans_failed ?? 0 },
    { label: 'Model Unavailable', value: metricsData.open_vocab_model_unavailable ?? 0 },
  ]

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Phase 23</p>
          <h2>Open-Vocabulary Scanner</h2>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{
            padding: '2px 8px', borderRadius: 3, fontSize: '0.65rem', fontWeight: 700, letterSpacing: 1,
            background: enabled ? '#052e16' : '#1f2937',
            color: enabled ? '#34d399' : '#9ca3af',
            border: `1px solid ${enabled ? '#065f46' : '#374151'}`,
          }}>
            {enabled ? 'ENABLED' : 'DISABLED'}
          </span>
          <span style={{
            padding: '2px 8px', borderRadius: 3, fontSize: '0.65rem', fontWeight: 700, letterSpacing: 1,
            background: adapterAvailable ? '#052e16' : '#1c1917',
            color: adapterAvailable ? '#34d399' : '#f87171',
            border: `1px solid ${adapterAvailable ? '#065f46' : '#7f1d1d'}`,
          }}>
            {adapterAvailable ? 'MODEL READY' : 'MODEL UNAVAILABLE'}
          </span>
        </div>
      </div>

      <div style={{ padding: '8px 12px' }}>
        {/* Adapter info */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10, fontSize: '0.75rem' }}>
          <span style={{ color: '#6b7280' }}>
            Provider: <strong style={{ color: '#d1d5db' }}>{adapterStatus.provider || '—'}</strong>
          </span>
          <span style={{ color: '#6b7280' }}>
            Model: <strong style={{ color: '#d1d5db' }}>{adapterStatus.model_id || '—'}</strong>
          </span>
          {adapterStatus.device && (
            <span style={{ color: '#6b7280' }}>
              Device: <strong style={{ color: '#d1d5db' }}>{adapterStatus.device}</strong>
            </span>
          )}
        </div>

        {/* Degraded banner */}
        {!adapterAvailable && (
          <div style={{
            background: '#431407', border: '1px solid #7c2d12', borderRadius: 4,
            padding: '6px 10px', marginBottom: 10, fontSize: '0.72rem', color: '#fdba74',
          }}>
            Model unavailable — scans will return degraded results.
            {reason && <span style={{ color: '#9ca3af', marginLeft: 6 }}>Reason: {reason}</span>}
          </div>
        )}

        {/* Metrics grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 8 }}>
          {metricRows.map(({ label, value }) => (
            <div key={label} style={{
              background: '#0a0f1a', borderRadius: 4, padding: '6px 10px',
              border: '1px solid #1c2535',
            }}>
              <p style={{ margin: 0, fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1 }}>
                {label}
              </p>
              <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: '#e5e7eb' }}>
                {value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
