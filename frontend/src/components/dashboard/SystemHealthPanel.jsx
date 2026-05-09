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

export default function SystemHealthPanel({ health, metrics = {}, error, websocketStatus }) {
  const status = health?.status || 'unknown'

  return (
    <section className="panel system-health-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Runtime Health</p>
          <h2>Supervisor View</h2>
        </div>
        <span className={`health-pill health-${status}`}>{status}</span>
      </div>
      {error && <ErrorState message={error} />}

      {/* Runtime / stream health */}
      <div className="health-grid">
        <MetricRow label="WebSocket"     value={websocketStatus || 'unknown'} />
        <MetricRow label="WS clients"    value={metrics.websocket_clients} />
        <MetricRow label="Dropped frames" value={metrics.frames_dropped} warn={(metrics.frames_dropped || 0) > 100} />
        <MetricRow label="Queue overflows" value={metrics.queue_overflows ?? metrics.queue_overflow_count} warn={(metrics.queue_overflows ?? metrics.queue_overflow_count ?? 0) > 10} />
        <MetricRow label="Circuit trips"  value={metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks} warn={(metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks ?? 0) > 0} />
        <MetricRow label="Generated"      value={formatDateTime(health?.generatedAt)} />
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
