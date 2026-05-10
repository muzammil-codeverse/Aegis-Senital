import { motion } from 'framer-motion'
import { BarChart3 } from 'lucide-react'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import AnalyticsExportPanel from './AnalyticsExportPanel'
import AnalyticsFilterBar from './AnalyticsFilterBar'
import AnomalyTrendPanel from './AnomalyTrendPanel'
import CameraRiskHeatmap from './CameraRiskHeatmap'
import CaseTrendChart from './CaseTrendChart'
import EventTrendChart from './EventTrendChart'
import ModelPerformancePanel from './ModelPerformancePanel'
import OperatorWorkloadPanel from './OperatorWorkloadPanel'
import RecentCriticalActivity from './RecentCriticalActivity'
import RiskRadarPanel from './RiskRadarPanel'
import StreamReliabilityPanel from './StreamReliabilityPanel'
import SystemPerformancePanel from './SystemPerformancePanel'
import ThreatOverviewCards from './ThreatOverviewCards'

function downloadExport(artifact) {
  const blob = new Blob([artifact.content || ''], { type: artifact.content_type || 'application/octet-stream' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = artifact.filename || `analytics_export.${artifact.format || 'json'}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

export default function AnalyticsCommandCenter({ analytics, canExport }) {
  const {
    overview,
    eventTimeseries,
    eventsByType,
    caseSummary,
    caseTimeseries,
    cameraRisk,
    cameraHeatmap,
    modelPerformance,
    anomalyTrends,
    identitySummary,
    openVocabSummary,
    streamReliability,
    operatorWorkload,
    systemPerformance,
    filters,
    setFilters,
    refresh,
    exportData,
    exporting,
    loading,
    error,
  } = analytics

  async function handleExport(payload) {
    const artifact = await exportData(payload)
    if (artifact) downloadExport(artifact)
  }

  if (loading && !overview) {
    return <LoadingState label="Loading analytics command center" />
  }

  return (
    <div className="analytics-shell">
      <motion.section
        className="panel analytics-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="analytics-hero-copy">
          <p className="eyebrow">Advanced Analytics</p>
          <h2>Intelligence Operations Dashboard</h2>
          <p className="analytics-hero-text">
            Supervisor-grade overview of possible incidents, review queues, stream reliability, model behavior, and operator workload.
          </p>
        </div>
        <div className="analytics-hero-badge">
          <BarChart3 size={18} />
          <span>Operator-safe analytics</span>
        </div>
      </motion.section>

      <AnalyticsFilterBar
        filters={filters}
        loading={loading}
        onRefresh={() => refresh()}
        onChange={partial => setFilters(current => ({ ...current, ...partial }))}
        status={overview?.source_status || {}}
      />

      {error ? <ErrorState message={error} onRetry={() => refresh()} /> : null}
      {!overview ? <EmptyState message="Analytics sources are currently unavailable." /> : null}

      {overview ? (
        <>
          <ThreatOverviewCards overview={overview} />
          <div className="analytics-grid">
            <EventTrendChart eventTimeseries={eventTimeseries} eventsByType={eventsByType} />
            <CaseTrendChart caseSummary={caseSummary} caseTimeseries={caseTimeseries} />
            <RiskRadarPanel cameraRisk={cameraRisk} />
            <CameraRiskHeatmap cameraRisk={cameraRisk} cameraHeatmap={cameraHeatmap} />
            <ModelPerformancePanel
              modelPerformance={modelPerformance}
              identitySummary={identitySummary}
              openVocabSummary={openVocabSummary}
              systemPerformance={systemPerformance}
            />
            <AnomalyTrendPanel anomalyTrends={anomalyTrends} />
            <StreamReliabilityPanel streamReliability={streamReliability} />
            <OperatorWorkloadPanel operatorWorkload={operatorWorkload} />
            <SystemPerformancePanel systemPerformance={systemPerformance} />
            <RecentCriticalActivity
              overview={overview}
              cameraRisk={cameraRisk}
              anomalyTrends={anomalyTrends}
              identitySummary={identitySummary}
              openVocabSummary={openVocabSummary}
            />
            <AnalyticsExportPanel
              canExport={canExport}
              exporting={exporting}
              filters={filters}
              onExport={handleExport}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}
