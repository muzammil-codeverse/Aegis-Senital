/**
 * OpenVocabStatusPanel — shows scanner enabled/disabled state, adapter
 * availability, model load/unload controls, and key metrics.
 *
 * Phase 24: adds model control buttons (Load/Unload/Reload) and extended
 * adapter status fields (device, path-configured booleans, last load error).
 */

/** Badge component for status labels. */
function Badge({ label, variant = 'neutral' }) {
  const palettes = {
    ok:      { bg: '#052e16', color: '#34d399', border: '#065f46' },
    warn:    { bg: '#431407', color: '#fdba74', border: '#7c2d12' },
    error:   { bg: '#1f1010', color: '#f87171', border: '#7f1d1d' },
    neutral: { bg: '#1f2937', color: '#9ca3af', border: '#374151' },
  }
  const p = palettes[variant] || palettes.neutral
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 3, fontSize: '0.65rem', fontWeight: 700, letterSpacing: 1,
      background: p.bg, color: p.color, border: `1px solid ${p.border}`,
    }}>
      {label}
    </span>
  )
}

/** Small action button for model control operations. */
function ControlButton({ label, onClick, disabled, variant = 'default' }) {
  const colors = {
    default: { bg: '#1e3a5f', color: '#93c5fd', hover: '#1d4ed8' },
    danger:  { bg: '#3b1515', color: '#fca5a5', hover: '#7f1d1d' },
    success: { bg: '#052e16', color: '#6ee7b7', hover: '#065f46' },
  }
  const c = colors[variant] || colors.default
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: disabled ? '#111827' : c.bg,
        color: disabled ? '#4b5563' : c.color,
        border: `1px solid ${disabled ? '#1f2937' : c.hover}`,
        borderRadius: 4,
        padding: '4px 12px',
        fontSize: '0.7rem',
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        letterSpacing: 0.5,
      }}
    >
      {label}
    </button>
  )
}

export default function OpenVocabStatusPanel({
  status,
  loading,
  modelStatus,
  onLoad,
  onUnload,
  onReload,
  canWrite = false,
}) {
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

  // Phase 24 model-status fields
  const modelLoaded = modelStatus?.loaded === true
  const modelDevice = modelStatus?.device || adapterStatus.device
  const modelPathConfigured = modelStatus?.model_path_configured ?? false
  const processorPathConfigured = modelStatus?.processor_path_configured ?? false
  const lastLoadError = modelStatus?.last_load_error || (adapterAvailable ? null : reason)

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
          <p className="eyebrow">Phase 23 + 24</p>
          <h2>Open-Vocabulary Scanner</h2>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Badge label={enabled ? 'ENABLED' : 'DISABLED'} variant={enabled ? 'ok' : 'neutral'} />
          <Badge
            label={adapterAvailable ? 'MODEL READY' : 'MODEL UNAVAILABLE'}
            variant={adapterAvailable ? 'ok' : 'error'}
          />
          <Badge
            label={modelLoaded ? 'LOADED' : 'UNLOADED'}
            variant={modelLoaded ? 'ok' : 'warn'}
          />
        </div>
      </div>

      <div style={{ padding: '8px 12px' }}>
        {/* Adapter info row */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10, fontSize: '0.75rem' }}>
          <span style={{ color: '#6b7280' }}>
            Provider: <strong style={{ color: '#d1d5db' }}>{adapterStatus.provider || modelStatus?.provider || '—'}</strong>
          </span>
          <span style={{ color: '#6b7280' }}>
            Model: <strong style={{ color: '#d1d5db' }}>{adapterStatus.model_id || '—'}</strong>
          </span>
          {modelDevice && (
            <span style={{ color: '#6b7280' }}>
              Device: <strong style={{ color: modelDevice === 'cuda' ? '#34d399' : '#9ca3af' }}>{modelDevice}</strong>
            </span>
          )}
          <span style={{ color: '#6b7280' }}>
            Model Path: <strong style={{ color: modelPathConfigured ? '#34d399' : '#f87171' }}>
              {modelPathConfigured ? 'configured' : 'not set'}
            </strong>
          </span>
          <span style={{ color: '#6b7280' }}>
            Processor Path: <strong style={{ color: processorPathConfigured ? '#34d399' : '#f87171' }}>
              {processorPathConfigured ? 'configured' : 'not set'}
            </strong>
          </span>
        </div>

        {/* Degraded banner */}
        {!adapterAvailable && (
          <div style={{
            background: '#431407', border: '1px solid #7c2d12', borderRadius: 4,
            padding: '6px 10px', marginBottom: 10, fontSize: '0.72rem', color: '#fdba74',
          }}>
            Model unavailable — scans will return degraded results.
            {lastLoadError && <span style={{ color: '#9ca3af', marginLeft: 6 }}>Reason: {lastLoadError}</span>}
          </div>
        )}

        {/* Model control buttons — visible only to users with open_vocab:write */}
        {canWrite && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ color: '#4b5563', fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: 1, marginRight: 4 }}>
              Model Control
            </span>
            <ControlButton label="Load" onClick={onLoad} disabled={!onLoad || loading} variant="success" />
            <ControlButton label="Unload" onClick={onUnload} disabled={!onUnload || loading} variant="danger" />
            <ControlButton label="Reload" onClick={onReload} disabled={!onReload || loading} variant="default" />
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
