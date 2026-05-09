import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatNumber, metricValue } from '../../utils/formatters'

const METRICS = [
  ['frames_processed', 'Frames processed'],
  ['frames_dropped', 'Frames dropped'],
  ['queue_overflows', 'Queue overflows'],
  ['circuit_breaker_trips', 'Circuit trips'],
  ['id_switches', 'ID switches'],
  ['alerts_created', 'Alerts created'],
  ['alerts_dispatched', 'Alerts dispatched'],
  ['alerts_acknowledged', 'Alerts acknowledged'],
  ['notification_failures', 'Notify failures'],
  ['websocket_clients', 'WS clients'],
  ['avg_latency_ms', 'Avg latency'],
  ['max_latency_ms', 'Max latency'],
]

export default function MetricsPanel({ metrics = {}, loading, error, stale, onRetry }) {
  return (
    <section className="panel metrics-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Runtime Metrics</p>
          <h2>Core Counters</h2>
        </div>
        {stale && <span className="stale-pill">stale</span>}
      </div>
      {loading && <LoadingState label="Loading metrics" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      <div className="metric-strip">
        {METRICS.map(([key, label]) => (
          <div key={key} className="metric-tile">
            <span>{label}</span>
            <strong>{formatNumber(metricValue(metrics, key))}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
