import { useState, useEffect, useCallback } from 'react'
import MetricsPanel from '../components/dashboard/MetricsPanel'
import SystemHealthPanel from '../components/dashboard/SystemHealthPanel'
import { getSystemHealth } from '../api/metricsApi'

/**
 * SystemHealthPage — displays runtime health and metrics.
 * Phase 24: fetches detailed subsystem health from /api/system/health
 * and passes it to SystemHealthPanel for display.  Gracefully degrades
 * if the endpoint is unavailable.
 */
export default function SystemHealthPage({ metricsState, health, websocketState }) {
  const [systemHealth, setSystemHealth] = useState(null)
  const [systemHealthLoading, setSystemHealthLoading] = useState(false)

  const fetchSystemHealth = useCallback(async () => {
    setSystemHealthLoading(true)
    try {
      const result = await getSystemHealth()
      setSystemHealth(result)
    } catch {
      // Graceful degradation — do not crash the page
      setSystemHealth({ status: 'error', checks: {}, error: 'Health endpoint unavailable' })
    } finally {
      setSystemHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSystemHealth()
    // Refresh subsystem health every 30 seconds
    const interval = setInterval(fetchSystemHealth, 30000)
    return () => clearInterval(interval)
  }, [fetchSystemHealth])

  return (
    <div className="page-grid two-column">
      <SystemHealthPanel
        health={health}
        metrics={metricsState.metrics}
        error={metricsState.error}
        websocketStatus={websocketState.status}
        systemHealth={systemHealth}
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
