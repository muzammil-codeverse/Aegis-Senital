import ErrorState from '../common/ErrorState'
import { formatNumber } from '../../utils/formatters'
import { formatDateTime } from '../../utils/time'

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
      <div className="health-grid">
        <span>WebSocket</span><strong>{websocketStatus || 'unknown'}</strong>
        <span>WS clients</span><strong>{formatNumber(metrics.websocket_clients)}</strong>
        <span>Dropped frames</span><strong>{formatNumber(metrics.frames_dropped)}</strong>
        <span>Queue overflows</span><strong>{formatNumber(metrics.queue_overflows ?? metrics.queue_overflow_count)}</strong>
        <span>Circuit trips</span><strong>{formatNumber(metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks)}</strong>
        <span>Generated</span><strong>{formatDateTime(health?.generatedAt)}</strong>
      </div>
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
