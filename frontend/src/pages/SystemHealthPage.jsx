import MetricsPanel from '../components/dashboard/MetricsPanel'
import SystemHealthPanel from '../components/dashboard/SystemHealthPanel'

export default function SystemHealthPage({ metricsState, health, websocketState }) {
  return (
    <div className="page-grid two-column">
      <SystemHealthPanel
        health={health}
        metrics={metricsState.metrics}
        error={metricsState.error}
        websocketStatus={websocketState.status}
      />
      <MetricsPanel
        metrics={metricsState.metrics}
        loading={metricsState.loading}
        error={metricsState.error}
        stale={metricsState.stale}
        onRetry={metricsState.refresh}
      />
    </div>
  )
}
