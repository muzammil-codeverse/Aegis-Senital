import { formatNumber } from '../../utils/formatters'

export default function SystemPerformancePanel({ systemPerformance }) {
  const modelStates = Object.entries(systemPerformance?.model_states || {})

  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">System Runtime</p>
          <h2>Latency, GPU, and Event Bus</h2>
        </div>
        <span className={`health-pill health-${systemPerformance?.status || 'degraded'}`}>{systemPerformance?.status || 'unknown'}</span>
      </div>
      <div className="analytics-mini-grid">
        <article className="analytics-mini-tile"><span>GPU</span><strong>{systemPerformance?.gpu_name || systemPerformance?.gpu_status || 'unknown'}</strong></article>
        <article className="analytics-mini-tile"><span>Avg inference</span><strong>{systemPerformance?.avg_inference_latency_ms != null ? `${systemPerformance.avg_inference_latency_ms} ms` : 'N/A'}</strong></article>
        <article className="analytics-mini-tile"><span>Queue depth</span><strong>{formatNumber(systemPerformance?.queue_depth || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Active streams</span><strong>{formatNumber(systemPerformance?.active_streams || 0)}</strong></article>
      </div>
      <div className="analytics-inline-list">
        <article className="analytics-inline-card analytics-inline-card-wide">
          <strong>Event bus</strong>
          <span>{systemPerformance?.event_bus_health?.status || 'No status reported'}</span>
        </article>
        <article className="analytics-inline-card analytics-inline-card-wide">
          <strong>Model states</strong>
          <span>{modelStates.length ? modelStates.map(([name, state]) => `${name}: ${state}`).join(' | ') : 'No model state snapshot available'}</span>
        </article>
      </div>
    </section>
  )
}
