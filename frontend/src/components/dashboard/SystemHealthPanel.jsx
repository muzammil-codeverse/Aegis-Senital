import ErrorState from '../common/ErrorState'
import { formatNumber } from '../../utils/formatters'
import { formatDateTime } from '../../utils/time'

function MetricRow({ label, value, warn, alert }) {
  const display = value != null && value !== undefined ? formatNumber(value) : 'N/A'
  const color = alert ? '#ff7875' : warn ? '#fa8c16' : undefined
  return (
    <>
      <span style={{ color: color ? '#9ca3af' : undefined }}>{label}</span>
      <strong style={{ color }}>{display}</strong>
    </>
  )
}

/**
 * StatusCheckRow — renders a single subsystem health check entry.
 * Maps status strings to visual indicators: ok (green), degraded (amber),
 * error (red), unavailable (grey).
 */
function StatusCheckRow({ name, check }) {
  if (!check) return null
  const statusColors = {
    ok:          '#34d399',
    healthy:     '#34d399',
    degraded:    '#fbbf24',
    error:       '#f87171',
    failed:      '#f87171',
    unavailable: '#6b7280',
    disabled:    '#6b7280',
  }
  const dot = statusColors[check.status] || '#6b7280'
  const label = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4, fontSize: '0.72rem' }}>
      <span style={{
        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
        background: dot, marginTop: 3, flexShrink: 0,
      }} />
      <div>
        <span style={{ color: '#d1d5db', fontWeight: 600 }}>{label}</span>
        {check.detail && check.status !== 'ok' && (
          <span style={{ color: '#6b7280', marginLeft: 6 }}>{check.detail}</span>
        )}
        {check.status === 'ok' && check.detail && (
          <span style={{ color: '#4b5563', marginLeft: 6 }}>{check.detail}</span>
        )}
      </div>
    </div>
  )
}

function formatIsoDateTime(value) {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString([], { hour12: false })
}

function PersistenceStoreRow({ name, store }) {
  if (!store) return null
  const statusColors = {
    healthy: '#34d399',
    ok: '#34d399',
    degraded: '#fbbf24',
    failed: '#f87171',
    error: '#f87171',
    disabled: '#6b7280',
  }
  const color = statusColors[store.status] || '#6b7280'
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6, fontSize: '0.72rem' }}>
      <span style={{ color: '#d1d5db' }}>{name.replace(/_/g, ' ')}</span>
      <span style={{ color, textAlign: 'right' }}>
        {store.backend || 'unknown'} / {store.status || 'unknown'}
      </span>
    </div>
  )
}

export default function SystemHealthPanel({ health, metrics = {}, error, websocketStatus, systemHealth }) {
  const status = health?.status || 'unknown'

  // Phase 24: derive overall status from subsystem health if available
  const subsystemStatus = systemHealth?.status
  const checks = systemHealth?.checks || {}
  const healthEndpointUnavailable = systemHealth?.error != null && Object.keys(checks).length === 0
  const persistence = checks.persistence || systemHealth?.persistence || {}
  const persistenceStores = persistence?.stores || {}
  const persistenceWarnings = persistence?.warnings || []
  const persistenceFailures = persistence?.failures || []

  // Subsystem order for display
  const CHECK_ORDER = [
    'security', 'database', 'redis', 'storage', 'gpu',
    'model_registry', 'event_bus', 'open_vocab', 'segmentation',
  ]
  const segmentationCheck = checks.segmentation || {}

  return (
    <section className="panel system-health-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Runtime Health</p>
          <h2>Supervisor View</h2>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button type="button" className="text-button" onClick={() => { window.location.hash = 'analytics' }}>
            Analytics
          </button>
          <span className={`health-pill health-${status}`}>{status}</span>
          {subsystemStatus && subsystemStatus !== status && (
            <span className={`health-pill health-${subsystemStatus}`} style={{ fontSize: '0.6rem' }}>
              sys: {subsystemStatus}
            </span>
          )}
        </div>
      </div>
      {error && <ErrorState message={error} />}

      {/* Phase 24: subsystem health checks panel */}
      {healthEndpointUnavailable ? (
        <div style={{
          background: '#1c1917', border: '1px solid #3f2d1e', borderRadius: 4,
          padding: '8px 12px', margin: '8px 12px', fontSize: '0.72rem', color: '#fdba74',
        }}>
          Health endpoint unavailable — subsystem status not shown.
        </div>
      ) : Object.keys(checks).length > 0 ? (
        <div style={{ padding: '8px 12px 4px' }}>
          <p style={{ margin: '0 0 6px', fontSize: '0.62rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
            Subsystem Health
          </p>
          {CHECK_ORDER.map(key =>
            checks[key] ? <StatusCheckRow key={key} name={key} check={checks[key]} /> : null
          )}
          {Object.keys(checks).filter(k => !CHECK_ORDER.includes(k)).map(key => (
            <StatusCheckRow key={key} name={key} check={checks[key]} />
          ))}
          {systemHealth?.generated_at && (
            <p style={{ margin: '6px 0 0', fontSize: '0.6rem', color: '#374151' }}>
              Updated: {formatDateTime(systemHealth.generated_at * 1000)}
            </p>
          )}
        </div>
      ) : null}

      {persistence?.enabled !== false && Object.keys(persistenceStores).length > 0 ? (
        <div style={{ padding: '6px 12px 4px' }}>
          <p style={{ margin: '0 0 6px', fontSize: '0.62rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
            Persistence
          </p>
          <div style={{ marginBottom: 8, fontSize: '0.72rem', color: '#9ca3af' }}>
            Status: <span style={{ color: '#d1d5db' }}>{persistence.status || 'unknown'}</span>
            {'  '}| Retention: <span style={{ color: '#d1d5db' }}>{persistence.retention_mode || 'unknown'}</span>
            {'  '}| Last backup: <span style={{ color: '#d1d5db' }}>{formatIsoDateTime(persistence.last_backup_at)}</span>
          </div>
          {['cases', 'evidence_metadata', 'evidence_files', 'identity_registry', 'audit_logs', 'osint'].map(key => (
            <PersistenceStoreRow key={key} name={key} store={persistenceStores[key]} />
          ))}
          {persistenceFailures.length > 0 && (
            <div style={{ marginTop: 8, fontSize: '0.68rem', color: '#fca5a5' }}>
              {persistenceFailures.join(' | ')}
            </div>
          )}
          {persistenceWarnings.length > 0 && (
            <div style={{ marginTop: 6, fontSize: '0.68rem', color: '#fdba74' }}>
              {persistenceWarnings.join(' | ')}
            </div>
          )}
        </div>
      ) : null}

      {/* Runtime / stream health */}
      <div className="health-grid">
        <MetricRow label="WebSocket"     value={websocketStatus || 'unknown'} />
        <MetricRow label="WS clients"    value={metrics.websocket_clients} />
        <MetricRow label="Dropped frames" value={metrics.frames_dropped} warn={(metrics.frames_dropped || 0) > 100} />
        <MetricRow label="Queue overflows" value={metrics.queue_overflows ?? metrics.queue_overflow_count} warn={(metrics.queue_overflows ?? metrics.queue_overflow_count ?? 0) > 10} />
        <MetricRow label="Circuit trips"  value={metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks} warn={(metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks ?? 0) > 0} />
        <MetricRow label="Generated"      value={formatDateTime(health?.generatedAt)} />
      </div>

      <div style={{ marginTop: 10 }}>
        <p style={{ margin: '0 0 5px', fontSize: '0.62rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
          Segmentation
        </p>
        <div className="health-grid">
          <MetricRow label="Status" value={segmentationCheck.status || 'unknown'} warn={['degraded', 'disabled'].includes(segmentationCheck.status)} alert={['failed', 'error'].includes(segmentationCheck.status)} />
          <MetricRow label="Provider" value={segmentationCheck.provider || 'sam2'} />
          <MetricRow label="Loaded" value={segmentationCheck.loaded === true ? 'yes' : 'no'} warn={segmentationCheck.enabled && !segmentationCheck.loaded} />
          <MetricRow label="Requests" value={metrics.segmentation_requests_total} />
          <MetricRow label="Masks" value={metrics.segmentation_masks_generated_total} />
          <MetricRow label="Failures" value={metrics.segmentation_failures_total} warn={(metrics.segmentation_failures_total || 0) > 0} />
          <MetricRow label="Skipped" value={metrics.segmentation_skipped_total} />
          <MetricRow label="Latency ms" value={metrics.segmentation_latency_ms != null ? Number(metrics.segmentation_latency_ms).toFixed(1) : null} />
        </div>
      </div>

      {/* Camera health section */}
      <div style={{ marginTop: 10 }}>
        <p style={{ margin: '0 0 5px', fontSize: '0.62rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
          Camera Health
        </p>
        <div className="health-grid">
          <MetricRow label="Registered"     value={metrics.registered_cameras} />
          <MetricRow label="Active streams" value={metrics.active_streams} />
          <MetricRow label="Offline"        value={metrics.offline_cameras} warn={(metrics.offline_cameras || 0) > 0} />
          <MetricRow label="Degraded"       value={metrics.degraded_cameras} warn={(metrics.degraded_cameras || 0) > 0} />
          <MetricRow label="Stale frames"   value={metrics.stale_camera_frames} warn={(metrics.stale_camera_frames || 0) > 5} />
          <MetricRow label="Stream fails"   value={metrics.stream_start_failures} alert={(metrics.stream_start_failures || 0) > 0} />
          <MetricRow label="MJPEG clients"  value={metrics.active_mjpeg_clients} />
          <MetricRow label="MJPEG served"   value={metrics.mjpeg_frames_served} />
        </div>
      </div>

      {/* Degradation reasons */}
      <div className="health-reasons">
        {(health?.reasons || []).length === 0 ? (
          <span>No degradation reasons reported.</span>
        ) : (
          health.reasons.map(reason => <span key={reason}>{reason}</span>)
        )}
      </div>
    </section>
  )
}
