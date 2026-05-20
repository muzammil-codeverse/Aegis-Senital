import { useState, useEffect, useCallback } from 'react'
import CapabilityHealthPanel from '../components/dashboard/CapabilityHealthPanel'
import ExhibitionPreflightPanel from '../components/dashboard/ExhibitionPreflightPanel'
import MetricsPanel from '../components/dashboard/MetricsPanel'
import SystemHealthPanel from '../components/dashboard/SystemHealthPanel'
import { getCapabilities, getCapabilitySummary, refreshCapabilities } from '../api/capabilityApi'
import { getSystemHealth } from '../api/metricsApi'
import { getLatestPreflight, getPreflightSummary, runPreflight } from '../api/preflightApi'

/**
 * SystemHealthPage — displays runtime health and metrics.
 * Phase 24: fetches detailed subsystem health from /api/system/health
 * and passes it to SystemHealthPanel for display.  Gracefully degrades
 * if the endpoint is unavailable.
 */
export default function SystemHealthPage({ metricsState, health, websocketState }) {
  const [systemHealth, setSystemHealth] = useState(null)
  const [systemHealthLoading, setSystemHealthLoading] = useState(false)
  const [capabilities, setCapabilities] = useState([])
  const [capabilitySummary, setCapabilitySummary] = useState(null)
  const [capabilityLoading, setCapabilityLoading] = useState(false)
  const [capabilityError, setCapabilityError] = useState(null)
  const [preflightRun, setPreflightRun] = useState(null)
  const [preflightSummary, setPreflightSummary] = useState(null)
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [preflightRunningMode, setPreflightRunningMode] = useState(null)
  const [preflightError, setPreflightError] = useState(null)

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
    const timeout = window.setTimeout(fetchSystemHealth, 0)
    const interval = window.setInterval(fetchSystemHealth, 30000)
    return () => {
      window.clearTimeout(timeout)
      window.clearInterval(interval)
    }
  }, [fetchSystemHealth])

  const fetchCapabilities = useCallback(async ({ refresh = false } = {}) => {
    setCapabilityLoading(true)
    setCapabilityError(null)
    try {
      if (refresh) {
        const result = await refreshCapabilities()
        setCapabilities(result.items)
        setCapabilitySummary(result.summary)
      } else {
        const [itemsResult, summaryResult] = await Promise.all([
          getCapabilities(),
          getCapabilitySummary(),
        ])
        setCapabilities(itemsResult.items)
        setCapabilitySummary(summaryResult)
      }
    } catch (error) {
      setCapabilityError(error?.message || 'Capability status temporarily unavailable')
    } finally {
      setCapabilityLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeout = window.setTimeout(fetchCapabilities, 0)
    const interval = window.setInterval(fetchCapabilities, 30000)
    return () => {
      window.clearTimeout(timeout)
      window.clearInterval(interval)
    }
  }, [fetchCapabilities])

  const fetchPreflight = useCallback(async () => {
    setPreflightLoading(true)
    setPreflightError(null)
    try {
      const [latest, summary] = await Promise.all([
        getLatestPreflight(),
        getPreflightSummary(),
      ])
      setPreflightRun(latest)
      setPreflightSummary(summary)
    } catch (error) {
      setPreflightError(error?.message || 'Preflight readiness temporarily unavailable')
    } finally {
      setPreflightLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeout = window.setTimeout(fetchPreflight, 0)
    const interval = window.setInterval(fetchPreflight, 30000)
    return () => {
      window.clearTimeout(timeout)
      window.clearInterval(interval)
    }
  }, [fetchPreflight])

  const handleRunPreflight = useCallback(async (mode) => {
    setPreflightRunningMode(mode)
    setPreflightError(null)
    try {
      const result = await runPreflight(mode)
      setPreflightRun(result)
      const summary = await getPreflightSummary()
      setPreflightSummary(summary)
      await fetchCapabilities()
    } catch (error) {
      setPreflightError(error?.message || `${mode} preflight failed`)
    } finally {
      setPreflightRunningMode(null)
    }
  }, [fetchCapabilities])

  return (
    <div className="page-grid single-column">
      <ExhibitionPreflightPanel
        latestRun={preflightRun}
        summary={preflightSummary}
        loading={preflightLoading}
        runningMode={preflightRunningMode}
        error={preflightError}
        onRefresh={fetchPreflight}
        onRunQuick={() => handleRunPreflight('QUICK')}
        onRunExhibition={() => handleRunPreflight('EXHIBITION')}
      />
      <CapabilityHealthPanel
        capabilities={capabilities}
        summary={capabilitySummary}
        loading={capabilityLoading}
        error={capabilityError}
        onRefresh={() => fetchCapabilities({ refresh: true })}
      />
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
          loading={metricsState.loading || systemHealthLoading}
          error={metricsState.error}
          stale={metricsState.stale}
          onRetry={metricsState.refresh}
        />
      </div>
    </div>
  )
}
